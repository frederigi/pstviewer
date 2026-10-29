#!/usr/bin/env python3
"""
PST Viewer - Fase 2: Suite de Testes Reais (Banco MySQL, Autenticação Argon2id,
Isolamento entre Usuários, Encerramento Explícito e Limpeza de Sessões Abandonadas).
"""

from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import stat
import sys
import uuid

from sqlalchemy import delete, func, select

from app.auth.security import (
    AuthenticationError,
    AuthorizationError,
    CsrfValidationError,
    authenticate_user,
    create_user,
    validate_auth_session,
    verify_csrf_token,
)
from app.core.config import settings
from app.database.models import (
    AuditLog,
    PstAttachment,
    PstFolder,
    PstMessage,
    PstSession,
    User,
)
from app.database.session import SessionLocal, build_mysql_engine, verify_mysql_connection
from app.services.cleanup_service import (
    close_and_purge_user_session,
    sweep_expired_and_orphan_sessions,
)
from app.services.session_manager import (
    create_pst_session,
    get_owned_pst_session,
    resolve_session_dir,
    utc_now,
)


def cleanup_test_users(db) -> None:
    for uname in ("teste_alice", "teste_bob"):
        u = db.scalar(select(User).where(User.username == uname))
        if u:
            db.delete(u)
    db.commit()


def run_tests() -> dict:
    results = {}

    # 1. Proibição estrita de SQLite
    try:
        build_mysql_engine("sqlite:///tmp/proibido.db")
        raise AssertionError("SQLite deveria ter sido rejeitado!")
    except RuntimeError as exc:
        results["1_sqlite_blocked"] = f"OK ({exc})"

    with SessionLocal() as db:
        # 2. Conexão MySQL / MariaDB InnoDB
        conn_info = verify_mysql_connection(db)
        assert conn_info["database"] == settings.db_name
        results["2_mysql_connection"] = conn_info

        cleanup_test_users(db)

        # 3. Criação de usuários Argon2id, Login, Session Fixation e Lockout de Força Bruta
        alice = create_user(db, "teste_alice", "SenhaForte#Alice2026", "Alice Silva")
        bob = create_user(db, "teste_bob", "SenhaForte#Bob2026", "Bob Santos")
        assert alice.password_hash.startswith("$argon2id$")

        _, alice_auth_1, alice_token_1 = authenticate_user(
            db, "teste_alice", "SenhaForte#Alice2026", "10.0.0.10", "Mozilla/Test"
        )
        # Simula novo login enviando cookie anterior (teste anti-session-fixation)
        _, alice_auth_2, alice_token_2 = authenticate_user(
            db,
            "teste_alice",
            "SenhaForte#Alice2026",
            "10.0.0.10",
            "Mozilla/Test",
            previous_raw_token=alice_token_1,
        )
        assert alice_token_1 != alice_token_2
        try:
            validate_auth_session(db, alice_token_1)
            raise AssertionError("Token antigo deveria estar revogado após novo login!")
        except AuthenticationError:
            pass

        # Validação CSRF
        verify_csrf_token(alice_auth_2, alice_auth_2.csrf_token)
        try:
            verify_csrf_token(alice_auth_2, "token_csrf_falso")
            raise AssertionError("CSRF inválido deveria falhar!")
        except CsrfValidationError:
            pass

        # Teste de bloqueio após 5 falhas de senha para Bob
        for _ in range(settings.max_login_attempts):
            try:
                authenticate_user(db, "teste_bob", "SenhaErrada", "10.0.0.20")
            except AuthenticationError:
                pass

        try:
            authenticate_user(db, "teste_bob", "SenhaForte#Bob2026", "10.0.0.20")
            raise AssertionError("Conta de Bob deveria estar temporariamente bloqueada!")
        except AuthenticationError as exc:
            assert "bloqueada" in str(exc).lower()

        # Desbloqueia Bob para os testes seguintes de isolamento de sessão
        bob.failed_login_attempts = 0
        bob.locked_until = None
        db.commit()

        results["3_auth_argon2id_csrf_lockout"] = "OK"

        # 4. Criação de sessões PST temporárias isoladas e verificação de permissões 0700
        sess_alice = create_pst_session(
            db, alice.id, alice.username, "financeiro_alice.pst", alice_auth_2.id, "10.0.0.10"
        )
        sess_bob = create_pst_session(
            db, bob.id, bob.username, "juridico_bob.pst", None, "10.0.0.20"
        )

        dir_alice = resolve_session_dir(sess_alice.session_uuid)
        dir_bob = resolve_session_dir(sess_bob.session_uuid)
        mode_alice = stat.S_IMODE(os.stat(dir_alice).st_mode)
        assert mode_alice == 0o700, f"Permissão esperada 0700, encontrada {oct(mode_alice)}"

        # Cria arquivos temporários simulados e registros no MySQL para ambas as sessões
        for sess, s_dir in ((sess_alice, dir_alice), (sess_bob, dir_bob)):
            (s_dir / "original.pst").write_bytes(b"!BDN_SIMULATED_PST_CONTENT")
            (s_dir / "attachments" / "contrato.pdf").write_bytes(b"%PDF-1.4 fake")
            sess.status = "READY"
            db.commit()

            fld = PstFolder(
                pst_session_id=sess.id,
                name="Caixa de Entrada",
                full_path="/Caixa de Entrada",
                folder_role="INBOX",
                message_count=1,
            )
            db.add(fld)
            db.commit()
            db.refresh(fld)

            msg = PstMessage(
                pst_session_id=sess.id,
                folder_id=fld.id,
                subject="Assunto Confidencial",
                sender_email="remetente@empresa.local",
                body_plain="Conteúdo restrito à sessão",
                has_attachments=True,
                attachment_count=1,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)

            att = PstAttachment(
                pst_session_id=sess.id,
                message_id=msg.id,
                original_filename="contrato.pdf",
                safe_filename="contrato.pdf",
                mime_type="application/pdf",
                size_bytes=13,
                storage_rel_path="attachments/contrato.pdf",
            )
            db.add(att)
            db.commit()

        results["4_temporary_sessions_created"] = {
            "alice_uuid": sess_alice.session_uuid,
            "bob_uuid": sess_bob.session_uuid,
            "dir_permissions": oct(mode_alice),
        }

        # 5. Isolamento entre usuários: Bob tenta acessar ou encerrar a sessão de Alice
        try:
            get_owned_pst_session(
                db,
                session_uuid=sess_alice.session_uuid,
                user_id=bob.id,
                username=bob.username,
                ip_address="10.0.0.20",
            )
            raise AssertionError("Bob NÃO poderia acessar a sessão de Alice!")
        except AuthorizationError:
            pass

        try:
            close_and_purge_user_session(
                db,
                session_uuid=sess_alice.session_uuid,
                user_id=bob.id,
                username=bob.username,
                ip_address="10.0.0.20",
            )
            raise AssertionError("Bob NÃO poderia encerrar a sessão de Alice!")
        except AuthorizationError:
            pass

        # Verifica que o evento AUTHZ_DENIED foi registrado na auditoria
        denied_count = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.session_uuid == sess_alice.session_uuid,
                AuditLog.event_type == "AUTHZ_DENIED",
            )
        )
        assert denied_count and denied_count >= 2
        results["5_cross_user_isolation"] = f"OK ({denied_count} tentativas bloqueadas e auditadas)"

        # 6. Proteção contra Path Traversal
        try:
            resolve_session_dir("../../etc/passwd")
            raise AssertionError("Path traversal deveria ter sido bloqueado!")
        except AuthorizationError:
            results["6_path_traversal_blocked"] = "OK"

        # 7. Encerramento explícito da sessão de Alice ('Encerrar consulta')
        purge_res = close_and_purge_user_session(
            db,
            session_uuid=sess_alice.session_uuid,
            user_id=alice.id,
            username=alice.username,
            ip_address="10.0.0.10",
        )
        assert not dir_alice.exists(), "Diretório de Alice deveria ter sido removido!"
        alice_msgs_left = db.scalar(
            select(func.count(PstMessage.id)).where(PstMessage.pst_session_id == sess_alice.id)
        )
        assert alice_msgs_left == 0, "Mensagens de Alice deveriam ter sido excluídas do MySQL!"

        # Garante que Alice não consegue mais abrir a sessão encerrada
        try:
            get_owned_pst_session(db, sess_alice.session_uuid, alice.id, alice.username)
            raise AssertionError("Sessão encerrada não pode continuar acessível!")
        except AuthorizationError:
            pass

        # Garante que a sessão de Bob permaneceu intacta após a limpeza de Alice
        assert dir_bob.exists(), "Diretório de Bob não deveria ser afetado pela limpeza de Alice!"
        bob_msgs_count = db.scalar(
            select(func.count(PstMessage.id)).where(PstMessage.pst_session_id == sess_bob.id)
        )
        assert bob_msgs_count == 1
        results["7_explicit_close_and_isolation_preserved"] = purge_res

        # 8. Sessão abandonada (expiração por inatividade) + diretório órfão
        sess_bob.idle_expires_at = utc_now() - timedelta(minutes=5)
        db.commit()

        orphan_uuid = str(uuid.uuid4())
        orphan_dir = settings.sessions_dir / orphan_uuid
        orphan_dir.mkdir(parents=True, exist_ok=True)
        (orphan_dir / "lixo.tmp").write_text("orfao", encoding="utf-8")

        sweep_summary = sweep_expired_and_orphan_sessions(db)
        assert sess_bob.session_uuid in sweep_summary["purged_sessions"]
        assert orphan_uuid in sweep_summary["orphan_dirs_removed"]
        assert not dir_bob.exists(), "Diretório da sessão expirada de Bob deveria ter sido removido!"
        assert not orphan_dir.exists(), "Diretório órfão deveria ter sido removido!"

        bob_msgs_after = db.scalar(
            select(func.count(PstMessage.id)).where(PstMessage.pst_session_id == sess_bob.id)
        )
        assert bob_msgs_after == 0
        results["8_abandoned_session_and_orphan_sweep"] = sweep_summary

        # Limpa os usuários temporários de teste mantendo os logs de auditoria gerados
        cleanup_test_users(db)

    return results


if __name__ == "__main__":
    summary = run_tests()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(0)

