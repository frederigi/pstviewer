"""
Gerenciamento e Isolamento Estrito de Sessões Temporárias de Consulta PST (Seções 8, 9 e 10).
Garante que cada usuário acesse exclusivamente sua própria sessão ativa e que caminhos de disco
fiquem confinados em `/srv/pstviewer/sessions/<session_uuid>`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional
import uuid

try:
    import pwd
except ImportError:
    pwd = None  # type: ignore

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import AuthorizationError
from app.core.audit import record_audit_event
from app.core.config import settings
from app.database.models import PstSession, SystemSetting

ACTIVE_READABLE_STATUSES = ("READY_PARTIAL", "READY")
ACTIVE_ALL_STATUSES = ("UPLOADING", "VALIDATING", "QUEUED", "PROCESSING", "READY_PARTIAL", "READY")

SAFE_LABEL_RE = re.compile(r"[^a-zA-Z0-9._\-\sÀ-ÿ]")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_system_settings_map(db: Session) -> Dict[str, str]:
    rows = db.scalars(select(SystemSetting)).all()
    return {r.setting_key: r.setting_value for r in rows}


def get_int_setting(db: Session, key: str, default: int) -> int:
    row = db.get(SystemSetting, key)
    if not row:
        return default
    try:
        return int(row.setting_value)
    except ValueError:
        return default


def sanitize_display_label(filename: str) -> str:
    base = os.path.basename(filename or "arquivo.pst").strip()
    cleaned = SAFE_LABEL_RE.sub("_", base)
    return (cleaned[:115] or "arquivo.pst")


def ensure_app_user_ownership(path: Path) -> None:
    """
    Se um comando/teste CLI for executado como root (uid 0), ajusta o dono do diretório/arquivo
    para o usuário dedicado `pstviewer`, garantindo que o serviço systemd `pstviewer-worker`
    consiga ler e limpar os arquivos sem PermissionError.
    """
    if pwd is not None and hasattr(os, "geteuid") and os.geteuid() == 0:
        try:
            pw = pwd.getpwnam("pstviewer")
            os.chown(path, pw.pw_uid, pw.pw_gid)
        except Exception:
            pass


def resolve_session_dir(session_uuid: str, base_dir: Path | None = None) -> Path:
    """
    Resolve com segurança o diretório da sessão e impede qualquer tentativa de Path Traversal.
    """
    try:
        parsed_uuid = str(uuid.UUID(session_uuid, version=4))
    except ValueError as exc:
        raise AuthorizationError("Identificador de sessão inválido.") from exc

    root = (base_dir or settings.sessions_dir).resolve()
    target = (root / parsed_uuid).resolve()
    if not target.is_relative_to(root) or target == root:
        raise AuthorizationError("Tentativa de Path Traversal bloqueada.")
    return target


def check_available_disk_space(db: Session, extra_required_bytes: int = 0) -> Dict[str, int]:
    """
    Verifica espaço livre no volume de `/srv/pstviewer/sessions` antes de aceitar novo upload.
    """
    root = settings.sessions_dir
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    min_free_mb = get_int_setting(db, "min_free_disk_mb", 15360)
    min_free_bytes = min_free_mb * 1024 * 1024

    if (usage.free - extra_required_bytes) < min_free_bytes:
        raise RuntimeError(
            f"Espaço livre insuficiente no servidor para iniciar nova sessão temporária "
            f"(Livre: {usage.free // (1024 * 1024)} MB, Mínimo seguro exigido: {min_free_mb} MB)."
        )
    return {
        "total_mb": usage.total // (1024 * 1024),
        "used_mb": usage.used // (1024 * 1024),
        "free_mb": usage.free // (1024 * 1024),
        "min_free_mb": min_free_mb,
    }


def create_pst_session(
    db: Session,
    user_id: int,
    username: str,
    original_filename: str,
    auth_session_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> PstSession:
    """
    Cria uma nova sessão temporária de consulta PST isolada por usuário,
    com diretório exclusivo permissão 0700 em `/srv/pstviewer/sessions/<uuid>`.
    """
    check_available_disk_space(db)

    now = utc_now()
    idle_min = get_int_setting(db, "session_idle_timeout_min", 30)
    hard_min = get_int_setting(db, "session_hard_timeout_min", 240)

    session_uuid = str(uuid.uuid4())
    session_dir = resolve_session_dir(session_uuid)

    # Cria estrutura física protegida com 0700
    session_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(session_dir, 0o700)
    ensure_app_user_ownership(session_dir)
    for sub in ("attachments", "temporary"):
        sub_path = session_dir / sub
        sub_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(sub_path, 0o700)
        ensure_app_user_ownership(sub_path)

    pst_session = PstSession(
        session_uuid=session_uuid,
        user_id=user_id,
        auth_session_id=auth_session_id,
        status="UPLOADING",
        storage_rel_path=session_uuid,
        display_label=sanitize_display_label(original_filename),
        created_at=now,
        last_heartbeat_at=now,
        idle_expires_at=now + timedelta(minutes=idle_min),
        hard_expires_at=now + timedelta(minutes=hard_min),
    )
    db.add(pst_session)
    db.commit()
    db.refresh(pst_session)

    record_audit_event(
        db,
        event_type="SESSION_CREATED",
        event_result="SUCCESS",
        user_id=user_id,
        username=username,
        session_uuid=session_uuid,
        ip_address=ip_address,
        details={
            "idle_expires_at": pst_session.idle_expires_at.isoformat(),
            "hard_expires_at": pst_session.hard_expires_at.isoformat(),
        },
    )
    return pst_session


def get_owned_pst_session(
    db: Session,
    session_uuid: str,
    user_id: int,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    require_readable: bool = False,
    touch_heartbeat: bool = True,
) -> PstSession:
    """
    Valida no MySQL que a sessão PST existe, pertence ao `user_id` autenticado,
    não está encerrada/expirada e renova o heartbeat se solicitado.
    Qualquer tentativa de acesso cruzado entre usuários gera auditoria `AUTHZ_DENIED`.
    """
    now = utc_now()
    pst_sess = db.scalar(select(PstSession).where(PstSession.session_uuid == session_uuid))

    if not pst_sess:
        record_audit_event(
            db,
            event_type="AUTHZ_DENIED",
            event_result="FAILURE",
            user_id=user_id,
            username=username,
            session_uuid=session_uuid,
            ip_address=ip_address,
            details={"reason": "session_not_found"},
        )
        raise AuthorizationError("Sessão de consulta não encontrada ou indisponível.")

    if pst_sess.user_id != user_id:
        record_audit_event(
            db,
            event_type="AUTHZ_DENIED",
            event_result="FAILURE",
            user_id=user_id,
            username=username,
            session_uuid=session_uuid,
            ip_address=ip_address,
            details={
                "reason": "cross_user_access_attempt",
                "owner_user_id": pst_sess.user_id,
            },
        )
        raise AuthorizationError("Acesso negado: esta sessão pertence a outro usuário.")

    if pst_sess.status in ("CLOSING", "CLEANING", "PURGED", "CANCELLED"):
        raise AuthorizationError("Esta sessão de consulta já foi encerrada e seus dados foram descartados.")

    if pst_sess.idle_expires_at <= now or pst_sess.hard_expires_at <= now:
        raise AuthorizationError("Esta sessão de consulta expirou por tempo limite.")

    if require_readable and pst_sess.status not in ACTIVE_READABLE_STATUSES:
        raise AuthorizationError(
            f"A sessão ainda não está pronta para leitura (estado atual: {pst_sess.status})."
        )

    if touch_heartbeat and pst_sess.status == "READY":
        elapsed = (now - pst_sess.last_heartbeat_at).total_seconds() if pst_sess.last_heartbeat_at else 999
        if elapsed >= 60:
            idle_min = get_int_setting(db, "session_idle_timeout_min", 30)
            new_idle = min(now + timedelta(minutes=idle_min), pst_sess.hard_expires_at)
            pst_sess.last_heartbeat_at = now
            pst_sess.idle_expires_at = new_idle
            db.commit()

    return pst_sess


def list_user_active_sessions(db: Session, user_id: int) -> List[PstSession]:
    now = utc_now()
    stmt = (
        select(PstSession)
        .where(
            PstSession.user_id == user_id,
            PstSession.status.in_(ACTIVE_ALL_STATUSES),
            PstSession.idle_expires_at > now,
            PstSession.hard_expires_at > now,
        )
        .order_by(PstSession.created_at.desc())
    )
    return list(db.scalars(stmt).all())

