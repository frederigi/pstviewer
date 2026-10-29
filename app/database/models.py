"""
Modelos ORM SQLAlchemy mapeados para MySQL / MariaDB (InnoDB).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    auth_sessions: Mapped[List["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    pst_sessions: Mapped[List["PstSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="auth_sessions")


class PstSession(Base):
    __tablename__ = "pst_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_uuid: Mapped[str] = mapped_column(CHAR(36), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    auth_session_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("auth_sessions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum(
            "UPLOADING",
            "VALIDATING",
            "QUEUED",
            "PROCESSING",
            "READY_PARTIAL",
            "READY",
            "CANCELLED",
            "CLOSING",
            "CLEANING",
            "PURGED",
            "FAILED",
            "CLEANUP_ERROR",
            name="pst_session_status",
        ),
        nullable=False,
        default="UPLOADING",
    )
    pst_format: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    file_sha256: Mapped[Optional[str]] = mapped_column(CHAR(64), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    disk_usage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_rel_path: Mapped[str] = mapped_column(String(128), nullable=False)
    display_label: Mapped[str] = mapped_column(String(120), nullable=False)
    total_folders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_folders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_attachments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_attachments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    corrupted_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    current_stage: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    diagnostic_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    hard_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    purged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="pst_sessions")
    folders: Mapped[List["PstFolder"]] = relationship(
        back_populates="pst_session", cascade="all, delete-orphan"
    )
    messages: Mapped[List["PstMessage"]] = relationship(
        back_populates="pst_session", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["PstAttachment"]] = relationship(
        back_populates="pst_session", cascade="all, delete-orphan"
    )
    jobs: Mapped[List["BackgroundJob"]] = relationship(
        back_populates="pst_session", cascade="all, delete-orphan"
    )


class PstFolder(Base):
    __tablename__ = "pst_folders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pst_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pst_sessions.id", ondelete="CASCADE"), nullable=False
    )
    parent_folder_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("pst_folders.id", ondelete="CASCADE"), nullable=True
    )
    pff_identifier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    folder_role: Mapped[str] = mapped_column(
        Enum("INBOX", "SENT", "DRAFTS", "TRASH", "ARCHIVE", "JUNK", "CUSTOM", name="folder_role"),
        nullable=False,
        default="CUSTOM",
    )
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    pst_session: Mapped["PstSession"] = relationship(back_populates="folders")
    messages: Mapped[List["PstMessage"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )


class PstMessage(Base):
    __tablename__ = "pst_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pst_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pst_sessions.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pst_folders.id", ondelete="CASCADE"), nullable=False
    )
    pff_message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    internet_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    recipients_to: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recipients_cc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recipients_bcc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attachment_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snippet: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    body_plain: Mapped[Optional[str]] = mapped_column(MEDIUMTEXT, nullable=True)
    body_html_sanitized: Mapped[Optional[str]] = mapped_column(MEDIUMTEXT, nullable=True)
    transport_headers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_eml_rel_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extraction_warnings: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    pst_session: Mapped["PstSession"] = relationship(back_populates="messages")
    folder: Mapped["PstFolder"] = relationship(back_populates="messages")
    attachments: Mapped[List["PstAttachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class PstAttachment(Base):
    __tablename__ = "pst_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pst_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pst_sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pst_messages.id", ondelete="CASCADE"), nullable=False
    )
    attachment_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    safe_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(127), nullable=False, default="application/octet-stream"
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[Optional[str]] = mapped_column(CHAR(64), nullable=True)
    storage_rel_path: Mapped[str] = mapped_column(String(255), nullable=False)
    extraction_status: Mapped[str] = mapped_column(
        Enum(
            "EXTRACTED",
            "TEXT_INDEXED",
            "ENCRYPTED_OR_PASSWORD",
            "CORRUPTED",
            "UNSUPPORTED_FORMAT",
            "SIZE_LIMIT_EXCEEDED",
            name="attachment_extraction_status",
        ),
        nullable=False,
        default="EXTRACTED",
    )
    is_inline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(MEDIUMTEXT, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    pst_session: Mapped["PstSession"] = relationship(back_populates="attachments")
    message: Mapped["PstMessage"] = relationship(back_populates="attachments")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pst_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pst_sessions.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(
        Enum("EXTRACT_PST", "INDEX_ATTACHMENTS", "CLEANUP_SESSION", name="job_type_enum"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum("PENDING", "RUNNING", "COMPLETED", "CANCELLED", "FAILED", name="job_status_enum"),
        nullable=False,
        default="PENDING",
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    worker_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    pst_session: Mapped["PstSession"] = relationship(back_populates="jobs")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    setting_value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    username_snapshot: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_uuid: Mapped[Optional[str]] = mapped_column(CHAR(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_result: Mapped[str] = mapped_column(
        Enum("SUCCESS", "FAILURE", "WARNING", name="audit_result_enum"), nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

