"""
Serviço de Limpeza e Descarte Seguro de Sessões Temporárias (Seção 9).
Responsável por:
  1. Encerrar imediatamente consultas a pedido do usuário ("Encerrar consulta" / "Sair").
  2. Expirar sessões abandonadas por tempo de inatividade ou duração máxima.
  3. Eliminar do disco o PST original, anexos e arquivos temporários.
  4. Remover do MySQL todas as pastas, mensagens e anexos temporários da sessão.
  5. Anonimizar metadados pessoais temporários na linha de controle da sessão.
  6. Registrar falhas e reagendar novas tentativas com backoff em `background_jobs`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import shutil
import stat
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import settings
from app.database.models import (
    AuditLog,
    BackgroundJob,
    PstAttachment,
    PstFolder,
    PstMessage,
    PstSession,
)
from app.services.session_manager import get_int_setting, get_owned_pst_session, resolve_session_dir


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _remove_readonly(func, path, _excinfo) -> None:
    """Garante remoção mesmo quando original.pst estiver travado como 0400 (somente leitura)."""
    try:
        os.chmod(path, stat.S_IRWXU)
        func(path)
    except Exception:
        pass


def _delete_session_db_records(db: Session, pst_session_id: int) -> Dict[str, int]:
    """Remove do MySQL todos os dados extraídos associados à sessão."""
    res_att = db.execute(
        delete(PstAttachment).where(PstAttachment.pst_session_id == pst_session_id)
    )
    res_msg = db.execute(
        delete(PstMessage).where(PstMessage.pst_session_id == pst_session_id)
    )
    res_fld = db.execute(
        delete(PstFolder).where(PstFolder.pst_session_id == pst_session_id)
    )
    return {
        "deleted_attachments": res_att.rowcount or 0,
        "deleted_messages": res_msg.rowcount or 0,
        "deleted_folders": res_fld.rowcount or 0,
    }


def _cancel_session_running_jobs(db: Session, pst_session_id: int, now: datetime) -> None:
    db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.pst_session_id == pst_session_id,
            BackgroundJob.job_type.in_(("EXTRACT_PST", "INDEX_ATTACHMENTS")),
            BackgroundJob.status.in_(("PENDING", "RUNNING")),
        )
        .values(
            cancel_requested=True,
            status="CANCELLED",
            finished_at=now,
        )
    )


def execute_session_purge(
    db: Session,
    pst_session: PstSession,
    reason: str = "USER_CLOSED",
    actor_user_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executa a limpeza física (disco) e lógica (MySQL) de uma sessão PST.
    Em caso de falha de I/O, marca CLEANUP_ERROR, registra alerta na auditoria
    e agenda tarefa de retentativa em `background_jobs`.
    """
    now = utc_now()
    session_uuid = pst_session.session_uuid

    pst_session.status = "CLEANING"
    if not pst_session.closed_at:
        pst_session.closed_at = now
    _cancel_session_running_jobs(db, pst_session.id, now)
    db.commit()

    try:
        session_dir = resolve_session_dir(session_uuid)
        disk_removed = False
        if session_dir.exists():
            shutil.rmtree(session_dir, onerror=_remove_readonly)
            disk_removed = True

        # Remove eventual arquivo parcial na quarentena com prefixo da sessão
        if settings.quarantine_dir.exists():
            for qfile in settings.quarantine_dir.glob(f"{session_uuid}*"):
                if qfile.is_dir():
                    shutil.rmtree(qfile, ignore_errors=True)
                else:
                    qfile.unlink(missing_ok=True)

        db_counts = _delete_session_db_records(db, pst_session.id)

        # Anonimiza o rótulo original do arquivo e zera uso em disco
        pst_session.display_label = "[REMOVIDO]"
        pst_session.file_sha256 = None
        pst_session.disk_usage_bytes = 0
        pst_session.current_stage = "Dados temporários eliminados"
        pst_session.diagnostic_summary = None
        pst_session.status = "PURGED"
        pst_session.purged_at = now

        # Marca eventuais jobs de limpeza pendentes como concluídos
        db.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.pst_session_id == pst_session.id,
                BackgroundJob.job_type == "CLEANUP_SESSION",
                BackgroundJob.status.in_(("PENDING", "RUNNING", "FAILED")),
            )
            .values(status="COMPLETED", finished_at=now)
        )
        db.commit()

        record_audit_event(
            db,
            event_type="SESSION_PURGED",
            event_result="SUCCESS",
            user_id=actor_user_id or pst_session.user_id,
            username=actor_username,
            session_uuid=session_uuid,
            ip_address=ip_address,
            details={
                "reason": reason,
                "disk_removed": disk_removed,
                **db_counts,
            },
        )
        return {
            "session_uuid": session_uuid,
            "status": "PURGED",
            "disk_removed": disk_removed,
            **db_counts,
        }

    except Exception as exc:
        db.rollback()
        err_msg = str(exc)[:500]
        pst_session = db.get(PstSession, pst_session.id)
        if pst_session:
            pst_session.status = "CLEANUP_ERROR"
            pst_session.current_stage = "Erro na limpeza; nova tentativa agendada"

            existing_job = db.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.pst_session_id == pst_session.id,
                    BackgroundJob.job_type == "CLEANUP_SESSION",
                    BackgroundJob.status.in_(("PENDING", "FAILED")),
                )
            )
            if existing_job:
                existing_job.attempts += 1
                existing_job.last_error = err_msg
                existing_job.status = "PENDING"
                existing_job.next_retry_at = now + timedelta(
                    minutes=min(30, 2 ** existing_job.attempts)
                )
            else:
                retry_job = BackgroundJob(
                    pst_session_id=pst_session.id,
                    job_type="CLEANUP_SESSION",
                    status="PENDING",
                    priority=1,
                    attempts=1,
                    max_attempts=10,
                    last_error=err_msg,
                    next_retry_at=now + timedelta(minutes=2),
                )
                db.add(retry_job)
            db.commit()

        record_audit_event(
            db,
            event_type="CLEANUP_ERROR",
            event_result="FAILURE",
            user_id=actor_user_id or (pst_session.user_id if pst_session else None),
            username=actor_username,
            session_uuid=session_uuid,
            ip_address=ip_address,
            details={"reason": reason, "error": err_msg},
        )
        raise


def close_and_purge_user_session(
    db: Session,
    session_uuid: str,
    user_id: int,
    username: str,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ação do botão 'Encerrar consulta': valida propriedade da sessão e executa expurgo imediato.
    """
    pst_sess = get_owned_pst_session(
        db,
        session_uuid=session_uuid,
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        require_readable=False,
        touch_heartbeat=False,
    )
    return execute_session_purge(
        db,
        pst_session=pst_sess,
        reason="USER_EXPLICIT_CLOSE",
        actor_user_id=user_id,
        actor_username=username,
        ip_address=ip_address,
    )


def close_all_user_sessions_on_logout(
    db: Session,
    user_id: int,
    username: str,
    ip_address: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Ação do botão 'Sair': encerra e expurga todas as sessões temporárias do usuário.
    """
    stmt = select(PstSession).where(
        PstSession.user_id == user_id,
        PstSession.status.not_in(("PURGED",)),
    )
    sessions = list(db.scalars(stmt).all())
    results: List[Dict[str, Any]] = []
    for sess in sessions:
        try:
            res = execute_session_purge(
                db,
                pst_session=sess,
                reason="USER_LOGOUT",
                actor_user_id=user_id,
                actor_username=username,
                ip_address=ip_address,
            )
            results.append(res)
        except Exception as exc:
            results.append({"session_uuid": sess.session_uuid, "error": str(exc)})
    return results


def sweep_expired_and_orphan_sessions(db: Session) -> Dict[str, Any]:
    """
    Rotina periódica independente (executada pelo daemon de limpeza):
      1. Identifica sessões com `idle_expires_at <= NOW()` ou `hard_expires_at <= NOW()`,
         ou em estado `CLOSING`, `CANCELLED`, `FAILED`, `CLEANUP_ERROR`.
      2. Executa o expurgo completo no disco e no MySQL.
      3. Remove diretórios órfãos em `/srv/pstviewer/sessions` que não pertençam a sessões ativas.
    """
    now = utc_now()
    stmt = select(PstSession).where(
        PstSession.status != "PURGED",
        or_(
            PstSession.idle_expires_at <= now,
            PstSession.hard_expires_at <= now,
            PstSession.status.in_(("CLOSING", "CANCELLED", "FAILED", "CLEANUP_ERROR")),
        ),
    )
    expired_sessions = list(db.scalars(stmt).all())

    purged_uuids: List[str] = []
    failed_uuids: List[str] = []

    for sess in expired_sessions:
        try:
            reason = "EXPIRED_TIMEOUT"
            if sess.status in ("CLOSING", "CANCELLED", "FAILED", "CLEANUP_ERROR"):
                reason = f"SWEEP_{sess.status}"
            execute_session_purge(db, pst_session=sess, reason=reason)
            purged_uuids.append(sess.session_uuid)
        except Exception:
            failed_uuids.append(sess.session_uuid)

    # Varredura de diretórios órfãos em /srv/pstviewer/sessions
    orphan_dirs_removed: List[str] = []
    if settings.sessions_dir.exists():
        active_uuids = set(
            db.scalars(
                select(PstSession.session_uuid).where(PstSession.status != "PURGED")
            ).all()
        )
        for child in settings.sessions_dir.iterdir():
            if not child.is_dir():
                continue
            dir_name = child.name
            try:
                uuid.UUID(dir_name, version=4)
            except ValueError:
                continue
            if dir_name not in active_uuids:
                shutil.rmtree(child, ignore_errors=True)
                orphan_dirs_removed.append(dir_name)
                record_audit_event(
                    db,
                    event_type="ORPHAN_DIR_PURGED",
                    event_result="SUCCESS",
                    session_uuid=dir_name,
                    details={"path": str(child)},
                )

    # Retenção de logs de auditoria
    retention_days = get_int_setting(db, "audit_retention_days", 90)
    cutoff = now - timedelta(days=retention_days)
    del_audit = db.execute(delete(AuditLog).where(AuditLog.event_time < cutoff))
    db.commit()

    return {
        "swept_at": now.isoformat(),
        "purged_sessions": purged_uuids,
        "failed_sessions": failed_uuids,
        "orphan_dirs_removed": orphan_dirs_removed,
        "expired_audit_logs_deleted": del_audit.rowcount or 0,
    }

