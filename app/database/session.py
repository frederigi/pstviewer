"""
Gerenciamento de conexões e sessões MySQL com SQLAlchemy.
Verifica que o dialeto seja exclusivamente MySQL/MariaDB.
"""

from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def build_mysql_engine(database_uri: str | None = None) -> Engine:
    uri = database_uri or settings.sqlalchemy_database_uri
    if not uri.startswith("mysql+pymysql://"):
        raise RuntimeError(
            "Violação de requisito: Apenas 'mysql+pymysql://' é permitido no PST Viewer."
        )
    return create_engine(
        uri,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=10,
        isolation_level="READ COMMITTED",
        future=True,
    )


engine: Engine = build_mysql_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dependency injection de sessão do MySQL para rotas FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_mysql_connection(db: Session) -> dict:
    """Confirma que o banco conectado é MySQL/MariaDB com suporte a InnoDB."""
    row = db.execute(text("SELECT VERSION() AS ver, DATABASE() AS db_name")).mappings().first()
    return {
        "version": row["ver"] if row else "unknown",
        "database": row["db_name"] if row else "unknown",
    }

