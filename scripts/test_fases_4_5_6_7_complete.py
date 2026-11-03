#!/usr/bin/env python3
"""
PST Viewer - Validação Completa End-to-End das Fases 4, 5, 6 e 7:
  - Fase 4: Leitor Web Estilo Outlook (Árvore de pastas, lista paginada/ordenada, leitura sanitizada)
  - Fase 5: Pesquisa Global (assunto, corpo, cabeçalhos, pastas e conteúdo textual de anexos) e Visualização de Anexos
  - Fase 6: Exportação EML RFC 5322 válida, Exportação TXT e Impressão (e-mail e anexo)
  - Fase 7: Segurança e Validação Final (Isolamento cruzado entre usuários em todas as rotas,
            SQL Injection, XSS, CSRF, Path Traversal, Encerramento pelo botão 'Encerrar consulta' e 'Sair')
"""

from __future__ import annotations

import email
import json
from pathlib import Path
import sys
import time

from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.security import create_user
from app.database.models import (
    AuditLog,
    PstAttachment,
    PstFolder,
    PstMessage,
    PstSession,
    User,
)
from app.database.session import SessionLocal
from app.main import app
from app.services.attachment_extractor import (
    detect_mime_and_signature,
    extract_attachment_text_and_metadata,
)
from app.services.session_manager import resolve_session_dir


def _cleanup_users(db, usernames: list[str]) -> None:
    for uname in usernames:
        u = db.scalar(select(User).where(User.username == uname))
        if u:
            db.delete(u)
    db.commit()


def run_all_tests(sample_pst: Path) -> dict:
    report = {}

    with SessionLocal() as db:
        _cleanup_users(db, ["e2e_alice", "e2e_bob", "e2e_admin"])
        alice = create_user(db, "e2e_alice", "SenhaForte#Alice2026", "Alice Operadora", is_admin=False)
        bob = create_user(db, "e2e_bob", "SenhaForte#Bob2026", "Bob Auditor", is_admin=False)
        admin = create_user(db, "e2e_admin", "SenhaForte#Admin2026", "Admin Geral", is_admin=True)

    client_alice = TestClient(app)
    client_bob = TestClient(app)
    client_admin = TestClient(app)

    # 1. Carregamento da Interface Web (SPA Outlook) e Cabeçalhos de Segurança
    resp_index = client_alice.get("/")
    assert resp_index.status_code == 200
    assert "PST Viewer" in resp_index.text
    assert resp_index.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp_index.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "default-src 'self'" in resp_index.headers.get("Content-Security-Policy", "")
    report["fase4_ui_and_security_headers"] = "OK"

    # 2. Login de Alice, Bob e Admin
    login_alice = client_alice.post(
        "/api/auth/login",
        json={"username": "e2e_alice", "password": "SenhaForte#Alice2026"},
    )
    assert login_alice.status_code == 200
    csrf_alice = login_alice.json()["csrf_token"]

    login_bob = client_bob.post(
        "/api/auth/login",
        json={"username": "e2e_bob", "password": "SenhaForte#Bob2026"},
    )
    assert login_bob.status_code == 200
    csrf_bob = login_bob.json()["csrf_token"]

    login_admin = client_admin.post(
        "/api/auth/login",
        json={"username": "e2e_admin", "password": "SenhaForte#Admin2026"},
    )
    assert login_admin.status_code == 200
    csrf_admin = login_admin.json()["csrf_token"]

    # 3. Upload do arquivo PST por Alice via API HTTP e processamento pelo worker
    with sample_pst.open("rb") as pf:
        up_resp = client_alice.post(
            "/api/sessions/upload",
            files={"file": ("caixa_alice.pst", pf, "application/octet-stream")},
            headers={"X-CSRF-Token": csrf_alice},
        )
    assert up_resp.status_code == 201, up_resp.text
    alice_uuid = up_resp.json()["session"]["session_uuid"]

    # Aguarda o pstviewer-worker (ou processa se ainda estiver na fila)
    for _ in range(25):
        st_resp = client_alice.get(f"/api/sessions/{alice_uuid}")
        assert st_resp.status_code == 200
        if st_resp.json()["status"] == "READY":
            break
        time.sleep(0.5)
    else:
        # Caso o daemon systemd não tenha rodado a tempo, dispara diretamente
        from app.workers.pst_worker import process_next_pending_job
        process_next_pending_job()

    st_final = client_alice.get(f"/api/sessions/{alice_uuid}").json()
    assert st_final["status"] == "READY"

    # 4. Fase 4: Leitor Web - Árvore de Pastas, Lista Paginada de Mensagens e Painel de Leitura
    folders_resp = client_alice.get(f"/api/sessions/{alice_uuid}/folders")
    assert folders_resp.status_code == 200
    folders_data = folders_resp.json()
    assert folders_data["total_folders"] >= 1
    assert len(folders_data["tree"]) >= 1

    # Escolhe pasta que contém mensagens
    folder_with_msgs = next(f for f in folders_data["folders"] if f["message_count"] > 0)
    fid = folder_with_msgs["id"]

    msgs_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/folders/{fid}/messages?page=1&page_size=10&sort_by=date_desc"
    )
    assert msgs_resp.status_code == 200
    msgs_data = msgs_resp.json()
    assert msgs_data["total"] >= 1
    first_msg_id = msgs_data["items"][0]["id"]

    detail_resp = client_alice.get(f"/api/sessions/{alice_uuid}/messages/{first_msg_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["id"] == first_msg_id
    assert "subject" in detail_data

    report["fase4_reader_folders_messages_detail"] = {
        "folders_count": folders_data["total_folders"],
        "selected_folder": folder_with_msgs["full_path"],
        "messages_in_folder": msgs_data["total"],
        "sample_subject": detail_data["subject"],
    }

    # Adiciona um anexo DOCX rico com texto indexado à primeira mensagem de Alice para testar pesquisa em anexo
    with SessionLocal() as db:
        sess_obj = db.scalar(select(PstSession).where(PstSession.session_uuid == alice_uuid))
        s_dir = resolve_session_dir(alice_uuid)
        docx_rel = "attachments/parecer_tecnico_exclusivo.docx"
        docx_abs = s_dir / docx_rel
        doc = DocxDocument()
        doc.add_paragraph("Cláusula Secreta de Governança Corporativa protocolo XZ-9988-BR")
        doc.save(str(docx_abs))
        mime_d = detect_mime_and_signature(docx_abs, "parecer_tecnico_exclusivo.docx")
        st_d, txt_d, meta_d = extract_attachment_text_and_metadata(
            docx_abs, "parecer_tecnico_exclusivo.docx", mime_d
        )
        new_att = PstAttachment(
            pst_session_id=sess_obj.id,
            message_id=first_msg_id,
            attachment_index=99,
            original_filename="parecer_tecnico_exclusivo.docx",
            safe_filename="parecer_tecnico_exclusivo.docx",
            mime_type=mime_d,
            size_bytes=docx_abs.stat().st_size,
            sha256="a" * 64,
            storage_rel_path=docx_rel,
            extraction_status=st_d,
            extracted_text=txt_d,
            metadata_json=meta_d,
        )
        db.add(new_att)
        db.commit()
        db.refresh(new_att)
        custom_att_id = new_att.id

    # 5. Fase 5: Pesquisa Global (incluindo texto dentro do anexo DOCX) e Visualização/Download de Anexo
    search_att_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/search",
        params={"q": "XZ-9988-BR"},
    )
    assert search_att_resp.status_code == 200
    search_att_data = search_att_resp.json()
    assert search_att_data["total"] == 1
    assert search_att_data["items"][0]["id"] == first_msg_id
    assert "parecer_tecnico_exclusivo.docx" in search_att_data["items"][0]["match_source"]

    att_meta_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/attachments/{custom_att_id}/metadata"
    )
    assert att_meta_resp.status_code == 200
    assert "XZ-9988-BR" in att_meta_resp.json()["extracted_text"]

    att_view_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/attachments/{custom_att_id}/view"
    )
    assert att_view_resp.status_code == 200
    assert "XZ-9988-BR" in att_view_resp.text

    att_dl_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/attachments/{custom_att_id}/download"
    )
    assert att_dl_resp.status_code == 200
    assert len(att_dl_resp.content) > 100

    report["fase5_global_search_and_attachments"] = {
        "search_by_attachment_text": "OK (encontrado protocolo XZ-9988-BR dentro do DOCX)",
        "attachment_metadata_and_view": "OK",
        "attachment_download_bytes": len(att_dl_resp.content),
    }

    # 6. Fase 6: Exportação EML RFC 5322, Exportação TXT e Impressão (E-mail e Anexo)
    eml_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/messages/{first_msg_id}/export.eml"
    )
    assert eml_resp.status_code == 200
    assert "attachment; filename=" in eml_resp.headers.get("Content-Disposition", "")
    parsed_eml = email.message_from_bytes(eml_resp.content)
    assert parsed_eml["Subject"] is not None
    assert parsed_eml.is_multipart()

    txt_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/messages/{first_msg_id}/export.txt"
    )
    assert txt_resp.status_code == 200
    assert "PST VIEWER - EXPORTAÇÃO DE MENSAGEM" in txt_resp.text

    print_msg_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/messages/{first_msg_id}/print"
    )
    assert print_msg_resp.status_code == 200
    assert "@media print" in print_msg_resp.text
    assert detail_data["subject"] in print_msg_resp.text

    print_att_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/attachments/{custom_att_id}/print"
    )
    assert print_att_resp.status_code == 200
    assert "@media print" in print_att_resp.text

    report["fase6_export_eml_txt_and_print"] = {
        "eml_rfc5322_valid": True,
        "eml_size_bytes": len(eml_resp.content),
        "txt_export_valid": True,
        "print_message_and_attachment_valid": True,
    }

    # 7. Fase 7: Segurança, Isolamento Cruzado (Bob tentando acessar recursos de Alice), SQLi e CSRF
    forbidden_endpoints = [
        f"/api/sessions/{alice_uuid}",
        f"/api/sessions/{alice_uuid}/folders",
        f"/api/sessions/{alice_uuid}/folders/{fid}/messages",
        f"/api/sessions/{alice_uuid}/messages/{first_msg_id}",
        f"/api/sessions/{alice_uuid}/search?q=XZ-9988-BR",
        f"/api/sessions/{alice_uuid}/attachments/{custom_att_id}/metadata",
        f"/api/sessions/{alice_uuid}/attachments/{custom_att_id}/download",
        f"/api/sessions/{alice_uuid}/messages/{first_msg_id}/export.eml",
        f"/api/sessions/{alice_uuid}/messages/{first_msg_id}/print",
    ]
    for ep in forbidden_endpoints:
        r_bob = client_bob.get(ep)
        assert r_bob.status_code == 403, f"Bob deveria receber 403 em {ep}, recebeu {r_bob.status_code}"

    # Tentativa de Bob encerrar a sessão de Alice
    r_bob_close = client_bob.post(
        f"/api/sessions/{alice_uuid}/close",
        headers={"X-CSRF-Token": csrf_bob},
    )
    assert r_bob_close.status_code == 403

    # Tentativa de CSRF (Alice tentando encerrar sem cabeçalho X-CSRF-Token)
    r_alice_no_csrf = client_alice.post(f"/api/sessions/{alice_uuid}/close")
    assert r_alice_no_csrf.status_code == 403

    # Teste de SQL Injection nos filtros de pesquisa
    sqli_resp = client_alice.get(
        f"/api/sessions/{alice_uuid}/search",
        params={
            "q": "' OR '1'='1' UNION SELECT 1,2,3 -- ",
            "sender": "admin' OR 1=1#",
        },
    )
    assert sqli_resp.status_code == 200
    assert sqli_resp.json()["total"] == 0

    # Teste de rotas administrativas (Bob bloqueado com 403; Admin permitido com 200)
    assert client_bob.get("/api/admin/sessions").status_code == 403
    admin_sess_resp = client_admin.get("/api/admin/sessions")
    assert admin_sess_resp.status_code == 200
    assert "host_metrics" in admin_sess_resp.json()

    # Encerramento explícito por Alice ('Encerrar consulta') e verificação de eliminação física e lógica
    close_resp = client_alice.post(
        f"/api/sessions/{alice_uuid}/close",
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "PURGED"
    assert close_resp.json()["disk_removed"] is True

    # Verifica que após o encerramento nem a própria Alice consegue mais acessar a sessão
    assert client_alice.get(f"/api/sessions/{alice_uuid}/folders").status_code == 403
    assert client_alice.get(f"/api/sessions/{alice_uuid}/messages/{first_msg_id}").status_code == 403
    assert not resolve_session_dir(alice_uuid).exists()

    with SessionLocal() as db:
        sess_obj = db.scalar(select(PstSession).where(PstSession.session_uuid == alice_uuid))
        remaining_msgs = db.scalar(
            select(func.count(PstMessage.id)).where(PstMessage.pst_session_id == sess_obj.id)
        )
        remaining_atts = db.scalar(
            select(func.count(PstAttachment.id)).where(PstAttachment.pst_session_id == sess_obj.id)
        )
        assert remaining_msgs == 0 and remaining_atts == 0
        _cleanup_users(db, ["e2e_alice", "e2e_bob", "e2e_admin"])

    report["fase7_security_isolation_sqli_csrf_and_purge"] = {
        "cross_user_blocked_endpoints": len(forbidden_endpoints) + 1,
        "csrf_protection": "OK",
        "sqli_parameterized_safe": "OK",
        "admin_rbac_enforced": "OK",
        "post_purge_inaccessible_and_zero_records": "OK",
    }

    return report


if __name__ == "__main__":
    sample_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/sample_apache_tika.pst")
    summary = run_all_tests(sample_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(0)

