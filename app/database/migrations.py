"""
Executor de migrações versionadas para o MySQL / MariaDB (Seção 8).
Mantém registro em `schema_migrations` e aplica `database/schema_v1.sql` de forma idempotente.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database.session import engine as default_engine

MIGRATIONS = [
    ("001_initial_schema", "schema_v1.sql"),
]


def ensure_migrations_table(db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    checksum CHAR(64) NOT NULL,
                    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """
            )
        )


def _split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt.endswith(";"):
                stmt = stmt[:-1].strip()
            if stmt:
                statements.append(stmt)
            current = []
    if current:
        rem = "\n".join(current).strip()
        if rem:
            statements.append(rem)
    return statements


def run_migrations(db_engine: Engine | None = None, sql_dir: Path | None = None) -> list[str]:
    target_engine = db_engine or default_engine
    base_dir = sql_dir or (Path(__file__).resolve().parents[2] / "database")
    ensure_migrations_table(target_engine)

    applied_now: list[str] = []
    with target_engine.begin() as conn:
        existing = {
            row[0]
            for row in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
        }

        for version, filename in MIGRATIONS:
            sql_path = base_dir / filename
            if not sql_path.is_file():
                raise FileNotFoundError(f"Arquivo de migração ausente: {sql_path}")
            content = sql_path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

            if version in existing:
                continue

            for stmt in _split_sql_statements(content):
                conn.execute(text(stmt))

            conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (:version, :checksum)"
                ),
                {"version": version, "checksum": checksum},
            )
            applied_now.append(version)

    return applied_now


if __name__ == "__main__":
    applied = run_migrations()
    if applied:
        print(f"[OK] Migrações aplicadas: {', '.join(applied)}")
    else:
        print("[OK] Banco MySQL já está na versão mais recente do schema.")
    sys.exit(0)

