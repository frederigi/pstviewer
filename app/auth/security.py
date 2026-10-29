"""
Segurança de Autenticação, Argon2id, Proteção contra Força Bruta,
Session Fixation e CSRF (Seção 10).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import settings
from app.database.models import AuthSession, User

# Configuração Argon2id recomendada pela OWASP (memória 64 MiB, 3 iterações, paralelismo 2)
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


class AuthenticationError(Exception):
    """Falha de autenticação ou conta temporariamente bloqueada."""


class AuthorizationError(Exception):
    """Acesso negado a sessão ou recurso de outro usuário."""


class CsrfValidationError(Exception):
    """Token CSRF ausente ou inválido."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(plain_password: str) -> str:
    if len(plain_password) < 8:
        raise ValueError("A senha deve possuir no mínimo 8 caracteres.")
    return _ph.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_user(
    db: Session,
    username: str,
    plain_password: str,
    full_name: str,
    is_admin: bool = False,
) -> User:
    clean_username = username.strip().lower()
    if not clean_username or len(clean_username) < 3:
        raise ValueError("Nome de usuário inválido (mínimo 3 caracteres).")

    existing = db.scalar(select(User).where(User.username == clean_username))
    if existing:
        raise ValueError(f"Usuário '{clean_username}' já existe.")

    user = User(
        username=clean_username,
        full_name=full_name.strip() or clean_username,
        password_hash=hash_password(plain_password),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(
    db: Session,
    username: str,
    plain_password: str,
    ip_address: str,
    user_agent: Optional[str] = None,
    previous_raw_token: Optional[str] = None,
) -> Tuple[User, AuthSession, str]:
    """
    Autentica o usuário com proteção contra força bruta e session fixation.
    Retorna (User, AuthSession, raw_session_token).
    """
    now = utc_now()
    clean_username = username.strip().lower()

    # Prevenção contra Session Fixation: se o cliente enviou um cookie prévio, revoga-o
    if previous_raw_token:
        revoke_auth_session_by_token(db, previous_raw_token)

    user = db.scalar(select(User).where(User.username == clean_username))
    if not user or not user.is_active:
        # Executa hash dummy para mitigar enumeração por tempo (timing attack)
        _ph.hash("dummy_password_for_constant_time_mitigation")
        record_audit_event(
            db,
            event_type="LOGIN_FAIL",
            event_result="FAILURE",
            username=clean_username,
            ip_address=ip_address,
            details={"reason": "invalid_user_or_inactive"},
        )
        raise AuthenticationError("Credenciais inválidas.")

    if user.locked_until and user.locked_until > now:
        record_audit_event(
            db,
            event_type="LOGIN_LOCKED",
            event_result="FAILURE",
            user_id=user.id,
            username=user.username,
            ip_address=ip_address,
            details={"locked_until": user.locked_until.isoformat()},
        )
        raise AuthenticationError(
            "Conta temporariamente bloqueada devido a múltiplas tentativas inválidas."
        )

    if not verify_password(plain_password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        db.commit()
        record_audit_event(
            db,
            event_type="LOGIN_FAIL",
            event_result="FAILURE",
            user_id=user.id,
            username=user.username,
            ip_address=ip_address,
            details={"failed_attempts": user.failed_login_attempts},
        )
        raise AuthenticationError("Credenciais inválidas.")

    # Atualiza hash caso parâmetros Argon2id tenham mudado
    if _ph.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(plain_password)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_hex(32)
    auth_session = AuthSession(
        session_token_hash=hash_session_token(raw_token),
        csrf_token=csrf_token,
        user_id=user.id,
        ip_address=ip_address[:45],
        user_agent=(user_agent[:255] if user_agent else None),
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=settings.auth_session_hours),
    )
    db.add(auth_session)
    db.commit()
    db.refresh(auth_session)

    record_audit_event(
        db,
        event_type="LOGIN",
        event_result="SUCCESS",
        user_id=user.id,
        username=user.username,
        ip_address=ip_address,
        details={"auth_session_id": auth_session.id},
    )
    return user, auth_session, raw_token


def validate_auth_session(
    db: Session,
    raw_token: str,
    touch_activity: bool = True,
) -> Tuple[User, AuthSession]:
    """Valida o token de sessão de autenticação e renova última atividade."""
    if not raw_token:
        raise AuthenticationError("Sessão não autenticada.")

    now = utc_now()
    token_hash = hash_session_token(raw_token)
    auth_sess = db.scalar(
        select(AuthSession).where(
            AuthSession.session_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if not auth_sess:
        raise AuthenticationError("Sessão inválida ou expirada.")

    user = db.get(User, auth_sess.user_id)
    if not user or not user.is_active:
        raise AuthenticationError("Usuário inativo.")

    if touch_activity:
        auth_sess.last_activity_at = now
        db.commit()

    return user, auth_sess


def verify_csrf_token(auth_session: AuthSession, supplied_csrf_token: Optional[str]) -> None:
    if not supplied_csrf_token or not hmac.compare_digest(
        auth_session.csrf_token, supplied_csrf_token
    ):
        raise CsrfValidationError("Falha de validação CSRF.")


def revoke_auth_session_by_token(db: Session, raw_token: str) -> Optional[AuthSession]:
    if not raw_token:
        return None
    token_hash = hash_session_token(raw_token)
    auth_sess = db.scalar(
        select(AuthSession).where(
            AuthSession.session_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        )
    )
    if auth_sess:
        auth_sess.revoked_at = utc_now()
        db.commit()
    return auth_sess

