"""
Rotas de Pesquisa Global no PST e Visualização/Download de Anexos (Seções 4 e 6):
  - Pesquisa global paginada com filtros por período, remetente, destinatário, pasta e anexos,
    abrangendo assunto, corpo, cabeçalhos, pastas, nomes de anexos e texto extraído dos anexos
    (GET /api/sessions/{session_uuid}/search)
  - Consulta de metadados e visualização textual/estruturada do anexo
    (GET /api/sessions/{session_uuid}/attachments/{attachment_id}/metadata)
  - Visualização segura do anexo no navegador (PDF, imagens, texto)
    (GET /api/sessions/{session_uuid}/attachments/{attachment_id}/view)
  - Download seguro do anexo com auditoria
    (GET /api/sessions/{session_uuid}/attachments/{attachment_id}/download)
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import desc, exists, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_auth
from app.auth.security import AuthorizationError
from app.core.audit import record_audit_event
from app.database.models import PstAttachment, PstFolder, PstMessage
from app.database.session import get_db
from app.services.session_manager import get_owned_pst_session, resolve_session_dir

router = APIRouter(prefix="/api/sessions/{session_uuid}", tags=["search_and_attachments"])

SAFE_INLINE_VIEW_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _extract_highlight_snippet(text: str | None, query: str | None, max_len: int = 240) -> str:
    if not text:
        return ""
    clean = " ".join(text.split())
    if not query:
        return clean[:max_len] + ("..." if len(clean) > max_len else "")
    idx = clean.lower().find(query.lower())
    if idx == -1:
        return clean[:max_len] + ("..." if len(clean) > max_len else "")
    start = max(0, idx - 70)
    end = min(len(clean), idx + len(query) + 140)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}"


@router.get("/search")
def search_session_messages(
    session_uuid: str,
    q: Optional[str] = Query(default=None, max_length=200),
    folder_id: Optional[int] = Query(default=None),
    sender: Optional[str] = Query(default=None, max_length=120),
    recipient: Optional[str] = Query(default=None, max_length=120),
    has_attachments: Optional[bool] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=150, ge=10, le=500),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Pesquisa global restrita exclusivamente à sessão PST atual do usuário autenticado (Seção 4).
    """
    try:
        pst_sess = get_owned_pst_session(
            db,
            session_uuid=session_uuid,
            user_id=auth.user.id,
            username=auth.user.username,
            ip_address=auth.ip_address,
            require_readable=True,
            touch_heartbeat=True,
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    conditions = [PstMessage.pst_session_id == pst_sess.id]

    if folder_id is not None:
        conditions.append(PstMessage.folder_id == folder_id)

    if sender and sender.strip():
        s_like = f"%{_escape_like(sender.strip())}%"
        conditions.append(
            or_(
                PstMessage.sender_name.ilike(s_like),
                PstMessage.sender_email.ilike(s_like),
            )
        )

    if recipient and recipient.strip():
        r_like = f"%{_escape_like(recipient.strip())}%"
        conditions.append(
            or_(
                PstMessage.recipients_to.ilike(r_like),
                PstMessage.recipients_cc.ilike(r_like),
                PstMessage.recipients_bcc.ilike(r_like),
            )
        )

    if has_attachments is not None:
        conditions.append(PstMessage.has_attachments.is_(has_attachments))

    if date_from and date_from.strip():
        try:
            dt_from = datetime.strptime(date_from.strip(), "%Y-%m-%d")
            conditions.append(PstMessage.received_at >= dt_from)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato inválido para date_from (use AAAA-MM-DD).",
            ) from exc

    if date_to and date_to.strip():
        try:
            dt_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            conditions.append(PstMessage.received_at <= dt_to)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato inválido para date_to (use AAAA-MM-DD).",
            ) from exc

    clean_q = q.strip() if q else ""
    att_match_map = {}
    if clean_q:
        q_like = f"%{_escape_like(clean_q)}%"
        # Pré-busca rápida de anexos e pastas desta sessão para evitar subqueries correlacionadas em OR
        att_rows = db.execute(
            select(
                PstAttachment.message_id,
                PstAttachment.original_filename,
                PstAttachment.extracted_text,
            ).where(
                PstAttachment.pst_session_id == pst_sess.id,
                or_(
                    PstAttachment.original_filename.ilike(q_like),
                    PstAttachment.extracted_text.ilike(q_like),
                ),
            )
        ).all()
        for mid, orig_fn, ext_txt in att_rows:
            if mid not in att_match_map:
                att_match_map[mid] = (orig_fn, ext_txt)

        matching_folder_ids = list(
            db.scalars(
                select(PstFolder.id).where(
                    PstFolder.pst_session_id == pst_sess.id,
                    PstFolder.full_path.ilike(q_like),
                )
            ).all()
        )

        or_clauses = [
            PstMessage.subject.ilike(q_like),
            PstMessage.body_plain.ilike(q_like),
            PstMessage.sender_name.ilike(q_like),
            PstMessage.sender_email.ilike(q_like),
            PstMessage.recipients_to.ilike(q_like),
            PstMessage.recipients_cc.ilike(q_like),
            PstMessage.recipients_bcc.ilike(q_like),
        ]
        if att_match_map:
            or_clauses.append(PstMessage.id.in_(list(att_match_map.keys())))
        if matching_folder_ids:
            or_clauses.append(PstMessage.folder_id.in_(matching_folder_ids))

        conditions.append(or_(*or_clauses))

    total = db.scalar(select(func.count(PstMessage.id)).where(*conditions)) or 0

    offset = (page - 1) * page_size
    stmt = (
        select(
            PstMessage.id,
            PstMessage.folder_id,
            PstMessage.subject,
            PstMessage.sender_name,
            PstMessage.sender_email,
            PstMessage.recipients_to,
            PstMessage.received_at,
            PstMessage.sent_at,
            PstMessage.importance,
            PstMessage.has_attachments,
            PstMessage.attachment_count,
            PstMessage.size_bytes,
            PstMessage.snippet,
            PstFolder.name.label("folder_name"),
            PstFolder.full_path.label("folder_path"),
        )
        .join(PstFolder, PstFolder.id == PstMessage.folder_id)
        .where(*conditions)
        .order_by(desc(PstMessage.received_at), desc(PstMessage.id))
        .offset(offset)
        .limit(page_size)
    )
    rows = db.execute(stmt).mappings().all()

    items = []
    for r in rows:
        mid = r["id"]
        match_source = "message"
        snippet_text = r["snippet"] or ""

        if clean_q and mid in att_match_map:
            orig_fn, ext_txt = att_match_map[mid]
            match_source = f"anexo: {orig_fn}"
            att_snip = _extract_highlight_snippet(ext_txt, clean_q)
            if att_snip:
                snippet_text = f"[{orig_fn}] {att_snip}"

        items.append(
            {
                "id": mid,
                "folder_id": r["folder_id"],
                "folder_name": r["folder_name"],
                "folder_path": r["folder_path"],
                "subject": r["subject"] or "(Sem assunto)",
                "sender_name": r["sender_name"],
                "sender_email": r["sender_email"],
                "recipients_to": r["recipients_to"],
                "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
                "received_at": r["received_at"].isoformat() if r["received_at"] else None,
                "importance": r["importance"],
                "has_attachments": r["has_attachments"],
                "attachment_count": r["attachment_count"],
                "size_bytes": r["size_bytes"],
                "snippet": snippet_text,
                "match_source": match_source,
            }
        )

    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    return {
        "query": clean_q,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "items": items,
    }


def _get_verified_attachment(
    db: Session,
    session_uuid: str,
    attachment_id: int,
    auth: AuthContext,
) -> tuple:
    try:
        pst_sess = get_owned_pst_session(
            db,
            session_uuid=session_uuid,
            user_id=auth.user.id,
            username=auth.user.username,
            ip_address=auth.ip_address,
            require_readable=True,
            touch_heartbeat=True,
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    att = db.scalar(
        select(PstAttachment).where(
            PstAttachment.id == attachment_id,
            PstAttachment.pst_session_id == pst_sess.id,
        )
    )
    if not att:
        record_audit_event(
            db,
            event_type="AUTHZ_DENIED",
            event_result="FAILURE",
            user_id=auth.user.id,
            username=auth.user.username,
            session_uuid=session_uuid,
            ip_address=auth.ip_address,
            details={"reason": "invalid_or_foreign_attachment_id", "attachment_id": attachment_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anexo não encontrado nesta sessão.",
        )

    session_dir = resolve_session_dir(pst_sess.session_uuid)
    if not att.storage_rel_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Anexo indisponível em disco ({att.extraction_status}).",
        )
    abs_path = (session_dir / att.storage_rel_path).resolve()
    if not abs_path.is_relative_to(session_dir) or not abs_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo físico do anexo não encontrado na área temporária.",
        )

    return pst_sess, att, abs_path


@router.get("/attachments/{attachment_id}/metadata")
def get_attachment_metadata_and_preview(
    session_uuid: str,
    attachment_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Retorna os metadados técnicos, estado de extração e conteúdo textual extraído
    (permitindo visualizar e imprimir documentos DOCX, XLSX, PPTX, PDF, TXT, CSV, RTF no navegador).
    """
    _, att, _ = _get_verified_attachment(db, session_uuid, attachment_id, auth)
    can_view_native = att.mime_type in SAFE_INLINE_VIEW_MIMES

    status_labels = {
        "TEXT_INDEXED": "Conteúdo textual extraído e indexado para pesquisa",
        "EXTRACTED": "Extraído (visualização binária ou download disponível)",
        "ENCRYPTED_OR_PASSWORD": "Arquivo protegido por senha ou criptografado (leitura interna indisponível)",
        "CORRUPTED": "Arquivo corrompido ou parcialmente ilegível",
        "UNSUPPORTED_FORMAT": "Formato sem suporte para visualização interna; disponível para download",
        "SIZE_LIMIT_EXCEEDED": "Tamanho excede o limite de extração textual automática",
    }

    return {
        "id": att.id,
        "message_id": att.message_id,
        "original_filename": att.original_filename,
        "safe_filename": att.safe_filename,
        "mime_type": att.mime_type,
        "size_bytes": att.size_bytes,
        "sha256": att.sha256,
        "extraction_status": att.extraction_status,
        "extraction_status_description": status_labels.get(att.extraction_status, att.extraction_status),
        "can_view_native_inline": can_view_native,
        "has_extracted_text": bool(att.extracted_text),
        "extracted_text": att.extracted_text,
        "metadata": att.metadata_json or {},
    }


@router.get("/attachments/{attachment_id}/view")
def view_attachment_inline(
    session_uuid: str,
    attachment_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Abre o anexo para visualização segura no navegador quando o formato é seguro
    (PDF, imagens) ou retorna o texto extraído em UTF-8 para leitura segura.
    Nunca executa HTML bruto, scripts ou macros de anexos.
    """
    _, att, abs_path = _get_verified_attachment(db, session_uuid, attachment_id, auth)

    encoded_name = quote(att.safe_filename)
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store, max-age=0",
        "Content-Disposition": f"inline; filename=\"{att.safe_filename}\"; filename*=UTF-8''{encoded_name}",
        "Content-Security-Policy": (
            "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
            "object-src 'self'; media-src 'none'; script-src 'none';"
        ),
    }

    if att.mime_type in SAFE_INLINE_VIEW_MIMES:
        return FileResponse(
            path=str(abs_path),
            media_type=att.mime_type,
            headers=headers,
        )

    if att.extracted_text:
        return Response(
            content=att.extracted_text,
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"O formato '{att.mime_type}' ({att.extraction_status}) não possui renderização direta "
            "no navegador. Utilize a opção Baixar anexo."
        ),
    )


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    session_uuid: str,
    attachment_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Transfere o anexo diretamente ao computador do usuário com nome sanitizado e auditoria.
    """
    pst_sess, att, abs_path = _get_verified_attachment(db, session_uuid, attachment_id, auth)

    record_audit_event(
        db,
        event_type="DOWNLOAD_ATTACHMENT",
        event_result="SUCCESS",
        user_id=auth.user.id,
        username=auth.user.username,
        session_uuid=pst_sess.session_uuid,
        ip_address=auth.ip_address,
        details={
            "attachment_id": att.id,
            "message_id": att.message_id,
            "size_bytes": att.size_bytes,
            "sha256": att.sha256,
        },
    )

    encoded_name = quote(att.safe_filename)
    return FileResponse(
        path=str(abs_path),
        media_type="application/octet-stream",
        filename=att.safe_filename,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store, max-age=0",
            "Content-Disposition": f"attachment; filename=\"{att.safe_filename}\"; filename*=UTF-8''{encoded_name}",
        },
    )

