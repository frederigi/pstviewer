"""
Rotas Administrativas (Seção 15 - Telas 12, 13, 14 e 15):
  - Gerenciamento básico de usuários (listagem, criação, ativação/desbloqueio, redefinição de senha)
  - Configurações administrativas e limites de recursos
  - Estado das sessões temporárias e métricas de disco/RAM/CPU do servidor
  - Diagnóstico e execução imediata da limpeza de arquivos temporários
"""

from __future__ import annotations

import os
import shutil
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_admin, require_csrf
from app.auth.security import create_user, hash_password
from app.core.audit import record_audit_event
from app.core.config import settings
from app.database.models import AuditLog, PstSession, SystemSetting, User
from app.database.session import get_db
from app.services.cleanup_service import (
    execute_session_purge,
    sweep_expired_and_orphan_sessions,
)
from app.services.session_manager import utc_now

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    full_name: str = Field(..., min_length=2, max_length=120)
    password: str = Field(..., min_length=8, max_length=256)
    is_admin: bool = False


class ResetPasswordPayload(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=256)


class UpdateSettingsPayload(BaseModel):
    settings: Dict[str, str]


def _get_host_metrics() -> dict:
    usage = shutil.disk_usage(settings.sessions_dir if settings.sessions_dir.exists() else "/")
    load1, load5, load15 = (0.0, 0.0, 0.0)
    try:
        load1, load5, load15 = os.getloadavg()
    except Exception:
        pass

    mem_total_mb = 0
    mem_avail_mb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as mf:
            for line in mf:
                if line.startswith("MemTotal:"):
                    mem_total_mb = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    mem_avail_mb = int(line.split()[1]) // 1024
    except Exception:
        pass

    return {
        "cpu_count": os.cpu_count() or 1,
        "load_avg_1m": round(load1, 2),
        "load_avg_5m": round(load5, 2),
        "load_avg_15m": round(load15, 2),
        "mem_total_mb": mem_total_mb,
        "mem_available_mb": mem_avail_mb,
        "disk_total_mb": usage.total // (1024 * 1024),
        "disk_used_mb": usage.used // (1024 * 1024),
        "disk_free_mb": usage.free // (1024 * 1024),
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _admin: AuthContext = Depends(require_admin),
):
    users = list(db.scalars(select(User).order_by(User.username.asc())).all())
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "failed_login_attempts": u.failed_login_attempts,
                "locked_until": u.locked_until.isoformat() if u.locked_until else None,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(
    payload: CreateUserPayload,
    db: Session = Depends(get_db),
    admin: AuthContext = Depends(require_admin),
    _csrf: AuthContext = Depends(require_csrf),
):
    try:
        new_user = create_user(
            db,
            username=payload.username,
            plain_password=payload.password,
            full_name=payload.full_name,
            is_admin=payload.is_admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        event_type="ADMIN_CREATE_USER",
        event_result="SUCCESS",
        user_id=admin.user.id,
        username=admin.user.username,
        ip_address=admin.ip_address,
        details={"created_username": new_user.username, "is_admin": new_user.is_admin},
    )
    return {
        "id": new_user.id,
        "username": new_user.username,
        "full_name": new_user.full_name,
        "is_admin": new_user.is_admin,
        "is_active": new_user.is_active,
    }


@router.post("/users/{target_user_id}/toggle-active")
def admin_toggle_user(
    target_user_id: int,
    db: Session = Depends(get_db),
    admin: AuthContext = Depends(require_admin),
    _csrf: AuthContext = Depends(require_csrf),
):
    user = db.get(User, target_user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    if user.id == admin.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é permitido desativar a própria conta administrativa.",
        )

    user.is_active = not user.is_active
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    record_audit_event(
        db,
        event_type="ADMIN_TOGGLE_USER",
        event_result="SUCCESS",
        user_id=admin.user.id,
        username=admin.user.username,
        ip_address=admin.ip_address,
        details={"target_username": user.username, "is_active": user.is_active},
    )
    return {"id": user.id, "username": user.username, "is_active": user.is_active}


@router.post("/users/{target_user_id}/reset-password")
def admin_reset_password(
    target_user_id: int,
    payload: ResetPasswordPayload,
    db: Session = Depends(get_db),
    admin: AuthContext = Depends(require_admin),
    _csrf: AuthContext = Depends(require_csrf),
):
    user = db.get(User, target_user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    user.password_hash = hash_password(payload.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    record_audit_event(
        db,
        event_type="ADMIN_RESET_PASSWORD",
        event_result="SUCCESS",
        user_id=admin.user.id,
        username=admin.user.username,
        ip_address=admin.ip_address,
        details={"target_username": user.username},
    )
    return {"id": user.id, "username": user.username, "password_updated": True}


@router.delete("/users/{target_user_id}")
def admin_delete_user(
    target_user_id: int,
    db: Session = Depends(get_db),
    admin: AuthContext = Depends(require_admin),
    _csrf: AuthContext = Depends(require_csrf),
):
    user = db.get(User, target_user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    if user.id == admin.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é permitido excluir a própria conta administrativa em uso.",
        )

    target_username = user.username

    # Expurga eventuais sessões PST temporárias em disco pertencentes ao usuário antes da exclusão
    user_sessions = list(
        db.scalars(select(PstSession).where(PstSession.user_id == user.id)).all()
    )
    for pst_sess in user_sessions:
        if pst_sess.status != "PURGED":
            execute_session_purge(
                db,
                pst_sess,
                reason="USER_DELETED_BY_ADMIN",
                actor_user_id=admin.user.id,
                actor_username=admin.user.username,
                ip_address=admin.ip_address,
            )

    # Desvincula referências opcionais em configurações e logs de auditoria
    db.execute(
        update(SystemSetting)
        .where(SystemSetting.updated_by == user.id)
        .values(updated_by=None)
    )
    db.execute(
        update(AuditLog)
        .where(AuditLog.user_id == user.id)
        .values(user_id=None)
    )

    db.delete(user)
    db.commit()

    record_audit_event(
        db,
        event_type="ADMIN_DELETE_USER",
        event_result="SUCCESS",
        user_id=admin.user.id,
        username=admin.user.username,
        ip_address=admin.ip_address,
        details={"deleted_user_id": target_user_id, "deleted_username": target_username},
    )
    return {"deleted": True, "id": target_user_id, "username": target_username}


@router.get("/settings")
def admin_get_settings(
    db: Session = Depends(get_db),
    _admin: AuthContext = Depends(require_admin),
):
    rows = list(db.scalars(select(SystemSetting).order_by(SystemSetting.setting_key.asc())).all())
    return {
        "settings": [
            {
                "key": r.setting_key,
                "value": r.setting_value,
                "description": r.description,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
        "host_metrics": _get_host_metrics(),
    }


@router.put("/settings")
def admin_update_settings(
    payload: UpdateSettingsPayload,
    db: Session = Depends(get_db),
    admin: AuthContext = Depends(require_admin),
    _csrf: AuthContext = Depends(require_csrf),
):
    updated_keys = []
    for k, v in payload.settings.items():
        row = db.get(SystemSetting, k)
        if not row:
            continue
        try:
            int_val = int(str(v).strip())
            if int_val < 0:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Valor numérico inválido para '{k}'.",
            ) from exc
        row.setting_value = str(int_val)
        row.updated_by = admin.user.id
        updated_keys.append(k)

    db.commit()
    record_audit_event(
        db,
        event_type="ADMIN_UPDATE_SETTINGS",
        event_result="SUCCESS",
        user_id=admin.user.id,
        username=admin.user.username,
        ip_address=admin.ip_address,
        details={"updated_keys": updated_keys},
    )
    return {"updated_keys": updated_keys}


@router.get("/sessions")
def admin_list_sessions_and_diagnostics(
    db: Session = Depends(get_db),
    _admin: AuthContext = Depends(require_admin),
):
    """
    Exibe o estado operacional das sessões temporárias e diagnóstico de armazenamento
    sem expor o conteúdo dos e-mails dos usuários.
    """
    now = utc_now()
    stmt = (
        select(PstSession, User.username)
        .join(User, User.id == PstSession.user_id)
        .order_by(desc(PstSession.created_at))
        .limit(100)
    )
    rows = db.execute(stmt).all()

    sessions_out = []
    for s, uname in rows:
        sessions_out.append(
            {
                "session_uuid": s.session_uuid,
                "owner_username": uname,
                "status": s.status,
                "pst_format": s.pst_format,
                "file_size_bytes": s.file_size_bytes,
                "disk_usage_bytes": s.disk_usage_bytes,
                "processed_folders": s.processed_folders,
                "total_folders": s.total_folders,
                "processed_messages": s.processed_messages,
                "total_messages": s.total_messages,
                "corrupted_items": s.corrupted_items,
                "progress_percent": float(s.progress_percent or 0.0),
                "is_expired": bool(s.idle_expires_at <= now or s.hard_expires_at <= now),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "idle_expires_at": s.idle_expires_at.isoformat() if s.idle_expires_at else None,
                "hard_expires_at": s.hard_expires_at.isoformat() if s.hard_expires_at else None,
                "purged_at": s.purged_at.isoformat() if s.purged_at else None,
            }
        )

    audits = list(
        db.scalars(select(AuditLog).order_by(desc(AuditLog.event_time)).limit(60)).all()
    )

    return {
        "host_metrics": _get_host_metrics(),
        "sessions": sessions_out,
        "audit_logs": [
            {
                "id": a.id,
                "event_time": a.event_time.isoformat() if a.event_time else None,
                "username": a.username_snapshot,
                "session_uuid": a.session_uuid,
                "event_type": a.event_type,
                "event_result": a.event_result,
                "ip_address": a.ip_address,
                "details": a.details_json,
            }
            for a in audits
        ],
    }


@router.post("/cleanup/run")
def admin_trigger_cleanup(
    db: Session = Depends(get_db),
    admin: AuthContext = Depends(require_admin),
    _csrf: AuthContext = Depends(require_csrf),
):
    summary = sweep_expired_and_orphan_sessions(db)
    record_audit_event(
        db,
        event_type="ADMIN_MANUAL_CLEANUP",
        event_result="SUCCESS",
        user_id=admin.user.id,
        username=admin.user.username,
        ip_address=admin.ip_address,
        details={
            "purged_count": len(summary["purged_sessions"]),
            "orphan_dirs_count": len(summary["orphan_dirs_removed"]),
        },
    )
    return summary


@router.post("/sessions/{session_uuid}/force-purge")
def admin_force_purge_session(
    session_uuid: str,
    db: Session = Depends(get_db),
    admin: AuthContext = Depends(require_admin),
    _csrf: AuthContext = Depends(require_csrf),
):
    sess = db.scalar(select(PstSession).where(PstSession.session_uuid == session_uuid))
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada.")
    return execute_session_purge(
        db,
        pst_session=sess,
        reason="ADMIN_FORCED_PURGE",
        actor_user_id=admin.user.id,
        actor_username=admin.user.username,
        ip_address=admin.ip_address,
    )

