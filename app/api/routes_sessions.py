"""
Rotas de Sessões de Consulta PST:
  - Upload seguro em streaming com validação binária !BDN (POST /api/sessions/upload)
  - Acompanhamento de progresso e abertura progressiva (GET /api/sessions/{session_uuid})
  - Diagnóstico de arquivos inválidos ou parcialmente processados (GET /api/sessions/{session_uuid}/diagnostics)
  - Cancelamento de processamento com limpeza de parciais (POST /api/sessions/{session_uuid}/cancel)
  - Encerramento explícito da consulta (POST /api/sessions/{session_uuid}/close)
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Optional
from urllib.parse import unquote
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_auth, require_csrf
from app.auth.security import AuthorizationError
from app.database.session import get_db
from app.services.cleanup_service import close_and_purge_user_session
from app.services.pst_extractor import request_session_extraction_cancel
from app.services.session_manager import get_owned_pst_session, list_user_active_sessions
from app.services.upload_service import (
    STREAM_CHUNK_BYTES,
    InvalidPstFileError,
    receive_pst_upload_async,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _serialize_session(s) -> dict:
    diag = None
    if s.diagnostic_summary:
        try:
            diag = json.loads(s.diagnostic_summary)
        except Exception:
            diag = {"raw": s.diagnostic_summary}

    return {
        "session_uuid": s.session_uuid,
        "display_label": s.display_label,
        "status": s.status,
        "can_open_reader": s.status in ("READY_PARTIAL", "READY"),
        "is_indexing_in_background": s.status in ("PROCESSING", "READY_PARTIAL"),
        "pst_format": s.pst_format,
        "file_sha256": s.file_sha256,
        "file_size_bytes": s.file_size_bytes,
        "disk_usage_bytes": s.disk_usage_bytes,
        "total_folders": s.total_folders,
        "processed_folders": s.processed_folders,
        "total_messages": s.total_messages,
        "processed_messages": s.processed_messages,
        "total_attachments": s.total_attachments,
        "processed_attachments": s.processed_attachments,
        "corrupted_items": s.corrupted_items,
        "progress_percent": float(s.progress_percent or 0.0),
        "current_stage": s.current_stage,
        "diagnostics": diag,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "idle_expires_at": s.idle_expires_at.isoformat() if s.idle_expires_at else None,
        "hard_expires_at": s.hard_expires_at.isoformat() if s.hard_expires_at else None,
    }


async def _upload_file_chunk_iter(upload_file: UploadFile) -> AsyncIterator[bytes]:
    while True:
        chunk = await upload_file.read(STREAM_CHUNK_BYTES)
        if not chunk:
            break
        yield chunk


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_pst_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_csrf),
):
    """
    Recebe um arquivo PST enviado pelo usuário autenticado em streaming,
    valida a assinatura binária !BDN, calcula o SHA-256 e enfileira a extração.
    """
    try:
        pst_sess, job = await receive_pst_upload_async(
            db=db,
            user_id=auth.user.id,
            username=auth.user.username,
            original_filename=file.filename or "arquivo.pst",
            chunk_iterator=_upload_file_chunk_iter(file),
            auth_session_id=auth.auth_session.id,
            ip_address=auth.ip_address,
        )
    except InvalidPstFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=str(exc),
        ) from exc
    finally:
        await file.close()

    return {
        "session": _serialize_session(pst_sess),
        "job_id": job.id,
    }


@router.post("/upload-stream", status_code=status.HTTP_201_CREATED)
async def upload_pst_raw_stream(
    request: Request,
    x_file_name: Optional[str] = Header(default="arquivo.pst", alias="X-File-Name"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_csrf),
):
    """
    Recebe o arquivo PST diretamente via stream binário (sem buffering intermediário multipart),
    ideal para arquivos PST grandes de múltiplos gigabytes.
    """
    decoded_filename = unquote(x_file_name or "arquivo.pst")
    try:
        pst_sess, job = await receive_pst_upload_async(
            db=db,
            user_id=auth.user.id,
            username=auth.user.username,
            original_filename=decoded_filename,
            chunk_iterator=request.stream(),
            auth_session_id=auth.auth_session.id,
            ip_address=auth.ip_address,
        )
    except InvalidPstFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=str(exc),
        ) from exc

    return {
        "session": _serialize_session(pst_sess),
        "job_id": job.id,
    }


@router.get("")
def list_my_sessions(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    sessions = list_user_active_sessions(db, auth.user.id)
    return {"sessions": [_serialize_session(s) for s in sessions]}


@router.get("/{session_uuid}")
def get_session_status(
    session_uuid: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    try:
        sess = get_owned_pst_session(
            db,
            session_uuid=session_uuid,
            user_id=auth.user.id,
            username=auth.user.username,
            ip_address=auth.ip_address,
            require_readable=False,
            touch_heartbeat=True,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return _serialize_session(sess)


@router.get("/{session_uuid}/diagnostics")
def get_session_diagnostics(
    session_uuid: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Retorna diagnóstico detalhado da sessão PST (itens corrompidos, avisos de extração,
    anexos protegidos por senha e estado de leitura parcial/completa).
    """
    try:
        sess = get_owned_pst_session(
            db,
            session_uuid=session_uuid,
            user_id=auth.user.id,
            username=auth.user.username,
            ip_address=auth.ip_address,
            require_readable=False,
            touch_heartbeat=False,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return _serialize_session(sess)


@router.post("/{session_uuid}/cancel")
def cancel_session_processing(
    session_uuid: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_csrf),
):
    """
    Cancela um processamento PST em andamento ou na fila e elimina arquivos parciais.
    """
    try:
        return request_session_extraction_cancel(
            db,
            session_uuid=session_uuid,
            user_id=auth.user.id,
            username=auth.user.username,
            ip_address=auth.ip_address,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post("/{session_uuid}/close")
def close_session(
    session_uuid: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_csrf),
):
    """
    Ação do botão 'Encerrar consulta': encerra a sessão de consulta atual
    e elimina imediatamente os respectivos arquivos temporários e dados do MySQL.
    """
    try:
        result = close_and_purge_user_session(
            db,
            session_uuid=session_uuid,
            user_id=auth.user.id,
            username=auth.user.username,
            ip_address=auth.ip_address,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return result
