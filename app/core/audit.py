"""
Serviço de Auditoria e Privacidade (Seção 14).
Registra eventos operacionais e de segurança no MySQL e em arquivo de auditoria,
filtrando rigorosamente senhas, tokens, corpos de e-mail ou dados pessoais sensíveis.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import pwd
except ImportError:
    pwd = None  # type: ignore

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import AuditLog

FORBIDDEN_AUDIT_KEYS = {
    "password",
    "password_hash",
    "token",
    "session_token",
    "csrf_token",
    "body",
    "body_plain",
    "body_html",
    "body_html_sanitized",
    "extracted_text",
    "raw_content",
}


def _get_file_audit_logger() -> logging.Logger:
    logger = logging.getLogger("pstviewer.audit")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        try:
            audit_dir: Path = settings.log_dir / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            log_file = audit_dir / "audit.log"
            handler = logging.FileHandler(log_file, encoding="utf-8")
            if pwd is not None and hasattr(os, "geteuid") and os.geteuid() == 0:
                try:
                    pw = pwd.getpwnam("pstviewer")
                    os.chown(audit_dir, pw.pw_uid, pw.pw_gid)
                    if log_file.exists():
                        os.chown(log_file, pw.pw_uid, pw.pw_gid)
                except Exception:
                    pass
            formatter = logging.Formatter("%(asctime)sZ | %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except Exception:
            # Caso diretório ainda não esteja acessível, mantém saída padrão segura
            stream_handler = logging.StreamHandler()
            logger.addHandler(stream_handler)
    return logger


def sanitize_audit_details(details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Remove qualquer chave proibida e trunca strings longas para evitar vazamento de conteúdo."""
    if not details:
        return None
    clean: Dict[str, Any] = {}
    for k, v in details.items():
        if k.lower() in FORBIDDEN_AUDIT_KEYS:
            continue
        if isinstance(v, str) and len(v) > 250:
            clean[k] = v[:250] + "...[truncado]"
        else:
            clean[k] = v
    return clean


def record_audit_event(
    db: Session,
    event_type: str,
    event_result: str = "SUCCESS",
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    session_uuid: Optional[str] = None,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> AuditLog:
    """Grava registro de auditoria no MySQL e no log de auditoria em disco."""
    safe_details = sanitize_audit_details(details)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    entry = AuditLog(
        event_time=now,
        user_id=user_id,
        username_snapshot=(username[:64] if username else None),
        session_uuid=(session_uuid[:36] if session_uuid else None),
        event_type=event_type[:64],
        event_result=event_result if event_result in ("SUCCESS", "FAILURE", "WARNING") else "WARNING",
        ip_address=(ip_address[:45] if ip_address else None),
        details_json=safe_details,
    )
    db.add(entry)
    if commit:
        db.commit()

    log_payload = {
        "event_type": entry.event_type,
        "result": entry.event_result,
        "user_id": entry.user_id,
        "username": entry.username_snapshot,
        "session_uuid": entry.session_uuid,
        "ip": entry.ip_address,
        "details": safe_details,
    }
    _get_file_audit_logger().info(json.dumps(log_payload, ensure_ascii=False))
    return entry

