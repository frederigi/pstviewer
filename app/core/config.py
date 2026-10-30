"""
Configuração centralizada do PST Viewer.
Garante que o banco principal seja exclusivamente MySQL/MariaDB (InnoDB),
bloqueando explicitamente qualquer tentativa de uso de SQLite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote_plus


def _load_dotenv_file(env_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_path.is_file():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        values[key] = val
    return values


@dataclass(frozen=True)
class Settings:
    env: str
    app_name: str
    bind_host: str
    bind_port: int
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    sessions_dir: Path
    quarantine_dir: Path
    jobs_dir: Path
    log_dir: Path
    secret_key: str
    cookie_secure: Optional[bool]
    auth_session_hours: int
    max_login_attempts: int
    login_lockout_minutes: int

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Retorna a URI MySQL parametrizada com UTF8MB4. Proíbe SQLite."""
        if not self.db_host or not self.db_name or not self.db_user:
            raise RuntimeError(
                "Configuração de banco MySQL incompleta. Verifique PSTVIEWER_DB_*."
            )
        if "sqlite" in self.db_host.lower() or "sqlite" in self.db_name.lower():
            raise RuntimeError(
                "ERRO DE SEGURANÇA/ARQUITETURA: SQLite é estritamente proibido no PST Viewer."
            )
        encoded_user = quote_plus(self.db_user)
        encoded_pw = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{encoded_user}:{encoded_pw}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


def load_settings(env_file: Path | None = None) -> Settings:
    if env_file is not None:
        default_env_path = env_file
    elif os.environ.get("PSTVIEWER_ENV_FILE"):
        default_env_path = Path(os.environ["PSTVIEWER_ENV_FILE"])
    else:
        opt_env = Path("/opt/pstviewer/config/pstviewer.env")
        local_root = Path(__file__).resolve().parents[2]
        local_cfg_env = local_root / "config" / "pstviewer.env"
        local_dot_env = local_root / ".env"
        if opt_env.is_file():
            default_env_path = opt_env
        elif local_cfg_env.is_file():
            default_env_path = local_cfg_env
        else:
            default_env_path = local_dot_env
    file_vars = _load_dotenv_file(default_env_path)

    def get_val(key: str, default: str = "") -> str:
        return os.environ.get(key, file_vars.get(key, default))

    custom_db_uri = get_val("PSTVIEWER_DATABASE_URI", "")
    if custom_db_uri and "sqlite" in custom_db_uri.lower():
        raise RuntimeError(
            "ERRO DE ARQUITETURA: SQLite é proibido como banco principal, alternativo ou fallback."
        )

    return Settings(
        env=get_val("PSTVIEWER_ENV", "production"),
        app_name=get_val("PSTVIEWER_APP_NAME", "PST Viewer"),
        bind_host=get_val("PSTVIEWER_BIND_HOST", "127.0.0.1"),
        bind_port=int(get_val("PSTVIEWER_BIND_PORT", "8000")),
        db_host=get_val("PSTVIEWER_DB_HOST", "127.0.0.1"),
        db_port=int(get_val("PSTVIEWER_DB_PORT", "3306")),
        db_name=get_val("PSTVIEWER_DB_NAME", "pstviewer"),
        db_user=get_val("PSTVIEWER_DB_USER", "pstviewer_app"),
        db_password=get_val("PSTVIEWER_DB_PASSWORD", ""),
        sessions_dir=Path(get_val("PSTVIEWER_SESSIONS_DIR", "/srv/pstviewer/sessions")),
        quarantine_dir=Path(get_val("PSTVIEWER_QUARANTINE_DIR", "/srv/pstviewer/quarantine")),
        jobs_dir=Path(get_val("PSTVIEWER_JOBS_DIR", "/var/lib/pstviewer/jobs")),
        log_dir=Path(get_val("PSTVIEWER_LOG_DIR", "/var/log/pstviewer")),
        secret_key=get_val("PSTVIEWER_SECRET_KEY", ""),
        cookie_secure=(
            None
            if get_val("PSTVIEWER_COOKIE_SECURE", "auto").strip().lower() in ("auto", "")
            else get_val("PSTVIEWER_COOKIE_SECURE", "auto").strip().lower() in ("1", "true", "yes")
        ),
        auth_session_hours=int(get_val("PSTVIEWER_AUTH_SESSION_HOURS", "8")),
        max_login_attempts=int(get_val("PSTVIEWER_MAX_LOGIN_ATTEMPTS", "5")),
        login_lockout_minutes=int(get_val("PSTVIEWER_LOGIN_LOCKOUT_MINUTES", "15")),
    )


settings = load_settings()

