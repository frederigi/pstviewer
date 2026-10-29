"""
Dependências de autenticação, CSRF e autorização por sessão para rotas FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.security import (
    AuthenticationError,
    CsrfValidationError,
    validate_auth_session,
    verify_csrf_token,
)
from app.database.models import AuthSession, User
from app.database.session import get_db

SESSION_COOKIE_NAME = "pstviewer_session"


@dataclass
class AuthContext:
    user: User
    auth_session: AuthSession
    ip_address: str


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    if request.client and request.client.host:
        return request.client.host[:45]
    return "127.0.0.1"


def get_current_auth(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AuthContext:
    if not session_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória.",
        )
    try:
        user, auth_sess = validate_auth_session(db, session_cookie, touch_activity=True)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    return AuthContext(
        user=user,
        auth_session=auth_sess,
        ip_address=get_client_ip(request),
    )


def require_csrf(
    auth: AuthContext = Depends(get_current_auth),
    x_csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
) -> AuthContext:
    try:
        verify_csrf_token(auth.auth_session, x_csrf_token)
    except CsrfValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return auth


def require_admin(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
    if not auth.user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return auth

