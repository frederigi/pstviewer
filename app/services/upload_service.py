"""
Recebimento Seguro de Arquivos PST em Streaming, Validação Binária (!BDN),
Cálculo de SHA-256 e Enfileiramento de Extração (Fase 3 - Seções 2, 5, 9, 10 e 13).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
from typing import Any, AsyncIterator, BinaryIO, Dict, Tuple
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import settings
from app.database.models import BackgroundJob, PstSession
from app.services.cleanup_service import execute_session_purge
from app.services.session_manager import (
    check_available_disk_space,
    create_pst_session,
    ensure_app_user_ownership,
    get_int_setting,
    resolve_session_dir,
)

PST_MAGIC = b"!BDN"
MIN_PST_HEADER_BYTES = 564
STREAM_CHUNK_BYTES = 1024 * 1024  # 1 MiB


class InvalidPstFileError(ValueError):
    """Arquivo enviado não possui estrutura binária PST válida ou excede limites."""


def parse_pst_header_bytes(header: bytes) -> Dict[str, Any]:
    """
    Valida assinatura binária !BDN (0x21 0x42 0x44 0x4E) nos primeiros 564 bytes
    e identifica versão ANSI (32-bit) vs Unicode (64-bit) e método de codificação.
    """
    if len(header) < MIN_PST_HEADER_BYTES:
        raise InvalidPstFileError(
            "Arquivo inválido ou truncado: tamanho menor que o cabeçalho mínimo de um PST (564 bytes)."
        )
    if header[0:4] != PST_MAGIC:
        raise InvalidPstFileError(
            "Assinatura binária inválida: o arquivo enviado não é um PST válido do Microsoft Outlook (!BDN ausente)."
        )

    w_ver = int.from_bytes(header[10:12], byteorder="little", signed=False)
    if w_ver in (14, 15):
        pst_format = f"ANSI 32-bit (wVer={w_ver})"
        crypt_byte = header[472]
    elif w_ver >= 21:
        pst_format = f"Unicode 64-bit (wVer={w_ver})"
        crypt_byte = header[513]
    else:
        pst_format = f"PST Variante (wVer={w_ver})"
        crypt_byte = 0

    crypt_map = {
        0x00: "Nenhuma (0x00)",
        0x01: "Compressível/Permutação (0x01)",
        0x02: "Cíclica/Alta (0x02)",
    }
    return {
        "w_ver": w_ver,
        "pst_format": pst_format,
        "encryption": crypt_map.get(crypt_byte, f"Desconhecida/Restrita (0x{crypt_byte:02x})"),
    }


def _finalize_validated_upload(
    db: Session,
    pst_session: PstSession,
    quarantine_file: Path,
    total_bytes: int,
    sha256_hex: str,
    header_info: Dict[str, Any],
    user_id: int,
    username: str,
    ip_address: str | None,
) -> Tuple[PstSession, BackgroundJob]:
    session_dir = resolve_session_dir(pst_session.session_uuid)
    dest_pst = session_dir / "original.pst"

    shutil.move(str(quarantine_file), str(dest_pst))
    # Regra 5 da Seção 9: Os arquivos originais recebidos deverão permanecer inalterados (0400 read-only)
    os.chmod(dest_pst, 0o400)
    ensure_app_user_ownership(dest_pst)

    pst_session.status = "QUEUED"
    pst_session.pst_format = header_info["pst_format"]
    pst_session.file_sha256 = sha256_hex
    pst_session.file_size_bytes = total_bytes
    pst_session.disk_usage_bytes = total_bytes
    pst_session.current_stage = "Arquivo validado; aguardando início da extração"

    job = BackgroundJob(
        pst_session_id=pst_session.id,
        job_type="EXTRACT_PST",
        status="PENDING",
        priority=5,
    )
    db.add(job)
    db.commit()
    db.refresh(pst_session)
    db.refresh(job)

    record_audit_event(
        db,
        event_type="UPLOAD_DONE",
        event_result="SUCCESS",
        user_id=user_id,
        username=username,
        session_uuid=pst_session.session_uuid,
        ip_address=ip_address,
        details={
            "size_bytes": total_bytes,
            "sha256": sha256_hex,
            "pst_format": header_info["pst_format"],
            "job_id": job.id,
        },
    )
    return pst_session, job


async def receive_pst_upload_async(
    db: Session,
    user_id: int,
    username: str,
    original_filename: str,
    chunk_iterator: AsyncIterator[bytes],
    auth_session_id: int | None = None,
    ip_address: str | None = None,
) -> Tuple[PstSession, BackgroundJob]:
    """
    Recebe upload assíncrono (FastAPI UploadFile) em chunks de 1 MiB na quarentena,
    valida cabeçalho !BDN nos primeiros bytes, aplica limite de tamanho em tempo real
    e move para a área isolada da sessão. Se interrompido ou inválido, limpa tudo.
    """
    max_upload_mb = get_int_setting(db, "max_upload_size_mb", 5120)
    max_upload_bytes = max_upload_mb * 1024 * 1024

    pst_session = create_pst_session(
        db,
        user_id=user_id,
        username=username,
        original_filename=original_filename,
        auth_session_id=auth_session_id,
        ip_address=ip_address,
    )

    settings.quarantine_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    quarantine_file = settings.quarantine_dir / f"{pst_session.session_uuid}.part"

    hasher = hashlib.sha256()
    header_buf = bytearray()
    header_info: Dict[str, Any] | None = None
    total_bytes = 0

    try:
        with quarantine_file.open("wb") as out_f:
            os.chmod(quarantine_file, 0o600)
            async for chunk in chunk_iterator:
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > max_upload_bytes:
                    raise InvalidPstFileError(
                        f"O arquivo excede o tamanho máximo permitido ({max_upload_mb} MB)."
                    )

                if len(header_buf) < MIN_PST_HEADER_BYTES:
                    needed = MIN_PST_HEADER_BYTES - len(header_buf)
                    header_buf.extend(chunk[:needed])
                    if len(header_buf) >= MIN_PST_HEADER_BYTES and header_info is None:
                        header_info = parse_pst_header_bytes(bytes(header_buf))

                hasher.update(chunk)
                out_f.write(chunk)

        if header_info is None:
            header_info = parse_pst_header_bytes(bytes(header_buf))

        check_available_disk_space(db, extra_required_bytes=0)

        return _finalize_validated_upload(
            db=db,
            pst_session=pst_session,
            quarantine_file=quarantine_file,
            total_bytes=total_bytes,
            sha256_hex=hasher.hexdigest(),
            header_info=header_info,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
        )

    except Exception as exc:
        quarantine_file.unlink(missing_ok=True)
        execute_session_purge(
            db,
            pst_session=pst_session,
            reason="UPLOAD_FAILED_OR_INTERRUPTED",
            actor_user_id=user_id,
            actor_username=username,
            ip_address=ip_address,
        )
        record_audit_event(
            db,
            event_type="UPLOAD_FAIL",
            event_result="FAILURE",
            user_id=user_id,
            username=username,
            session_uuid=pst_session.session_uuid,
            ip_address=ip_address,
            details={"error": str(exc)[:240], "bytes_received": total_bytes},
        )
        raise


def receive_pst_upload_sync(
    db: Session,
    user_id: int,
    username: str,
    original_filename: str,
    file_obj: BinaryIO,
    auth_session_id: int | None = None,
    ip_address: str | None = None,
) -> Tuple[PstSession, BackgroundJob]:
    """Versão síncrona em streaming (útil para CLI/testes automatizados)."""
    max_upload_mb = get_int_setting(db, "max_upload_size_mb", 5120)
    max_upload_bytes = max_upload_mb * 1024 * 1024

    pst_session = create_pst_session(
        db,
        user_id=user_id,
        username=username,
        original_filename=original_filename,
        auth_session_id=auth_session_id,
        ip_address=ip_address,
    )

    settings.quarantine_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    quarantine_file = settings.quarantine_dir / f"{pst_session.session_uuid}.part"

    hasher = hashlib.sha256()
    header_buf = bytearray()
    header_info: Dict[str, Any] | None = None
    total_bytes = 0

    try:
        with quarantine_file.open("wb") as out_f:
            os.chmod(quarantine_file, 0o600)
            while True:
                chunk = file_obj.read(STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_upload_bytes:
                    raise InvalidPstFileError(
                        f"O arquivo excede o tamanho máximo permitido ({max_upload_mb} MB)."
                    )
                if len(header_buf) < MIN_PST_HEADER_BYTES:
                    needed = MIN_PST_HEADER_BYTES - len(header_buf)
                    header_buf.extend(chunk[:needed])
                    if len(header_buf) >= MIN_PST_HEADER_BYTES and header_info is None:
                        header_info = parse_pst_header_bytes(bytes(header_buf))

                hasher.update(chunk)
                out_f.write(chunk)

        if header_info is None:
            header_info = parse_pst_header_bytes(bytes(header_buf))

        check_available_disk_space(db, extra_required_bytes=0)

        return _finalize_validated_upload(
            db=db,
            pst_session=pst_session,
            quarantine_file=quarantine_file,
            total_bytes=total_bytes,
            sha256_hex=hasher.hexdigest(),
            header_info=header_info,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
        )

    except Exception as exc:
        quarantine_file.unlink(missing_ok=True)
        execute_session_purge(
            db,
            pst_session=pst_session,
            reason="UPLOAD_FAILED_OR_INTERRUPTED",
            actor_user_id=user_id,
            actor_username=username,
            ip_address=ip_address,
        )
        record_audit_event(
            db,
            event_type="UPLOAD_FAIL",
            event_result="FAILURE",
            user_id=user_id,
            username=username,
            session_uuid=pst_session.session_uuid,
            ip_address=ip_address,
            details={"error": str(exc)[:240], "bytes_received": total_bytes},
        )
        raise

