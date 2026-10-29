"""
Rotas de Autenticação (Login, Logout com limpeza de sessões temporárias e Perfil).
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import (
    SESSION_COOKIE_NAME,
    AuthContext,
    get_client_ip,
    get_current_auth,
    require_csrf,
)
from app.auth.security import (
    AuthenticationError,
    authenticate_user,
    revoke_auth_session_by_token,
)
from app.core.audit import record_audit_event
from app.core.config import settings
from app.database.session import get_db
from app.services.cleanup_service import close_all_user_sessions_on_logout

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    previous_cookie: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    ip_addr = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    try:
        user, auth_sess, raw_token = authenticate_user(
            db,
            username=payload.username,
            plain_password=payload.password,
            ip_address=ip_addr,
            user_agent=user_agent,
            previous_raw_token=previous_cookie,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_hours * 3600,
        path="/",
    )
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
        },
        "csrf_token": auth_sess.csrf_token,
        "expires_at": auth_sess.expires_at.isoformat(),
    }


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_csrf),
    session_cookie: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    """
    Encerra a sessão de autenticação ('Sair') e elimina imediatamente todas as
    consultas PST temporárias pertencentes ao usuário (Seção 9.1).
    """
    purged_sessions = close_all_user_sessions_on_logout(
        db,
        user_id=auth.user.id,
        username=auth.user.username,
        ip_address=auth.ip_address,
    )
    if session_cookie:
        revoke_auth_session_by_token(db, session_cookie)

    record_audit_event(
        db,
        event_type="LOGOUT",
        event_result="SUCCESS",
        user_id=auth.user.id,
        username=auth.user.username,
        ip_address=auth.ip_address,
        details={"purged_pst_sessions_count": len(purged_sessions)},
    )
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {
        "logged_out": True,
        "purged_sessions": purged_sessions,
    }


@router.get("/me")
def me(auth: AuthContext = Depends(get_current_auth)):
    return {
        "authenticated": True,
        "user": {
            "id": auth.user.id,
            "username": auth.user.username,
            "full_name": auth.user.full_name,
            "is_admin": auth.user.is_admin,
        },
        "csrf_token": auth.auth_session.csrf_token,
        "expires_at": auth.auth_session.expires_at.isoformat(),
    }

