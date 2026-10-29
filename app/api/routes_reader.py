"""
Rotas do Leitor de E-mails (Fase 4 - Seções 3.1, 3.2, 3.3, 3.4 e 8):
  - Árvore hierárquica de pastas da sessão (GET /api/sessions/{session_uuid}/folders)
  - Lista paginada e ordenada de mensagens de uma pasta (GET /api/sessions/{session_uuid}/folders/{folder_id}/messages)
  - Leitura completa de uma mensagem com cabeçalhos, corpo sanitizado, texto original e anexos
    (GET /api/sessions/{session_uuid}/messages/{message_id})
Todas as consultas validam no MySQL que a sessão e os IDs pertencem ao usuário autenticado.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path
import re
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_auth
from app.auth.security import AuthorizationError
from app.core.audit import record_audit_event
from app.database.models import PstAttachment, PstFolder, PstMessage
from app.database.session import get_db
from app.services.session_manager import get_owned_pst_session, resolve_session_dir

router = APIRouter(prefix="/api/sessions/{session_uuid}", tags=["reader"])


MAPI_SYSTEM_FOLDER_PREFIXES = (
    "spam search folder",
    "pesquisar raiz",
    "search root",
    "finder",
    "common views",
    "deferred action",
    "spooler queue",
    "views",
    "reminders",
    "lembretes",
    "sync issues",
    "problemas de sincronização",
    "problemas de sincronizacao",
)

MAPI_ROOT_WRAPPER_PREFIXES = (
    "início do arquivo de dados",
    "inicio do arquivo de dados",
    "top of outlook data file",
    "top of personal folders",
    "início de pastas particulares",
    "inicio de pastas particulares",
    "raiz do pst",
    "ipm_subtree",
    "root - mailbox",
)


def _normalize_role(name: str, current_role: str) -> str:
    norm = (name or "").strip().lower()
    if norm in ("caixa de entrada", "inbox", "entrada", "recebidos", "recebidas"):
        return "INBOX"
    if norm in ("itens enviados", "sent items", "sent", "enviados", "enviadas"):
        return "SENT"
    return current_role


def _is_mapi_system_folder(name: str) -> bool:
    norm = (name or "").strip().lower()
    return any(norm.startswith(p) for p in MAPI_SYSTEM_FOLDER_PREFIXES)


def _is_mapi_root_wrapper(name: str) -> bool:
    norm = (name or "").strip().lower()
    return any(norm.startswith(p) for p in MAPI_ROOT_WRAPPER_PREFIXES)


def _build_folder_tree(folders: List[PstFolder]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Constrói a árvore de pastas limpa para o usuário:
      1. Oculta pastas internas de sistema do MAPI (ex: 'SPAM Search Folder 2', 'Pesquisar Raiz').
      2. Oculta pastas vazias que não possuem nenhuma mensagem nem subpastas com mensagens
         (ex: 'Itens Excluídos' vazio criado automaticamente pelo Outlook ao exportar).
      3. Desembrulha o container técnico 'Início do arquivo de dados do Outlook' ('Top of Outlook data file')
         quando ele próprio não tem mensagens avulsas, exibindo direto as pastas reais do backup.
    """
    nodes_by_id: Dict[int, Dict[str, Any]] = {}
    raw_roots: List[Dict[str, Any]] = []

    for f in folders:
        nodes_by_id[f.id] = {
            "id": f.id,
            "parent_folder_id": f.parent_folder_id,
            "name": f.name,
            "full_path": f.full_path,
            "folder_role": _normalize_role(f.name, f.folder_role),
            "depth": f.depth,
            "message_count": f.message_count or 0,
            "sort_order": f.sort_order,
            "children": [],
        }

    for f in folders:
        node = nodes_by_id[f.id]
        if f.parent_folder_id and f.parent_folder_id in nodes_by_id:
            nodes_by_id[f.parent_folder_id]["children"].append(node)
        else:
            raw_roots.append(node)

    total_msgs_in_pst = sum((f.message_count or 0) for f in folders)

    def _prune_tree(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        kept: List[Dict[str, Any]] = []
        for node in nodes:
            if _is_mapi_system_folder(node["name"]) and node["message_count"] == 0:
                continue
            node["children"] = _prune_tree(node["children"])
            has_msgs_here = node["message_count"] > 0
            has_msgs_in_children = len(node["children"]) > 0
            # Se já existem mensagens extraídas no PST, oculta ramos 100% vazios
            if total_msgs_in_pst > 0 and not has_msgs_here and not has_msgs_in_children:
                continue
            kept.append(node)
        return kept

    cleaned_roots = _prune_tree(raw_roots)

    # 1. Desembrulha containers técnicos de topo do Outlook ('Início do arquivo de dados do Outlook')
    unwrapped_roots: List[Dict[str, Any]] = []
    for r in cleaned_roots:
        if _is_mapi_root_wrapper(r["name"]) and r["message_count"] == 0 and r["children"]:
            for child in r["children"]:
                child["parent_folder_id"] = None
                unwrapped_roots.append(child)
        else:
            unwrapped_roots.append(r)

    # 2. Se o Outlook recriou pastas-pai vazias acima da pasta que o usuário realmente fez backup
    #    (ex: 'Backups' [0 msgs] -> '05 - Maio' -> 'Entrada' / 'Enviadas'), avança direto até a pasta do backup!
    while (
        len(unwrapped_roots) == 1
        and unwrapped_roots[0]["message_count"] == 0
        and len(unwrapped_roots[0]["children"]) == 1
    ):
        only_child = unwrapped_roots[0]["children"][0]
        only_child["parent_folder_id"] = None
        unwrapped_roots = [only_child]

    # Recalcula a profundidade (depth) e gera a lista plana limpa na ordem da árvore
    flat_clean: List[Dict[str, Any]] = []

    def _reindex_depth(nodes: List[Dict[str, Any]], current_depth: int) -> None:
        for n in nodes:
            n["depth"] = current_depth
            flat_clean.append(
                {
                    "id": n["id"],
                    "parent_folder_id": n["parent_folder_id"],
                    "name": n["name"],
                    "full_path": n["full_path"],
                    "folder_role": n["folder_role"],
                    "depth": n["depth"],
                    "message_count": n["message_count"],
                }
            )
            if n["children"]:
                _reindex_depth(n["children"], current_depth + 1)

    _reindex_depth(unwrapped_roots, 0)
    return unwrapped_roots, flat_clean


@router.get("/folders")
def get_session_folders(
    session_uuid: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Retorna a hierarquia original de pastas e subpastas encontradas no PST,
    com contagens de mensagens e distinção por caminho completo.
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

    stmt = (
        select(PstFolder)
        .where(PstFolder.pst_session_id == pst_sess.id)
        .order_by(PstFolder.depth.asc(), PstFolder.sort_order.asc(), PstFolder.name.asc())
    )
    folders = list(db.scalars(stmt).all())
    tree, flat_list = _build_folder_tree(folders)

    return {
        "session_uuid": pst_sess.session_uuid,
        "session_status": pst_sess.status,
        "is_indexing_in_background": pst_sess.status == "READY_PARTIAL",
        "progress_percent": float(pst_sess.progress_percent or 0.0),
        "total_folders": len(flat_list),
        "folders": flat_list,
        "tree": tree,
    }


@router.get("/folders/{folder_id}/messages")
def list_folder_messages(
    session_uuid: str,
    folder_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=150, ge=10, le=500),
    sort_by: str = Query(
        default="date_desc",
        pattern="^(date_desc|date_asc|sender_asc|subject_asc|size_desc)$",
    ),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Lista paginada de mensagens de uma pasta específica (Seção 3.3).
    Não carrega corpos integrais nem todas as mensagens de uma só vez.
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

    folder = db.scalar(
        select(PstFolder).where(
            PstFolder.id == folder_id,
            PstFolder.pst_session_id == pst_sess.id,
        )
    )
    if not folder:
        record_audit_event(
            db,
            event_type="AUTHZ_DENIED",
            event_result="FAILURE",
            user_id=auth.user.id,
            username=auth.user.username,
            session_uuid=session_uuid,
            ip_address=auth.ip_address,
            details={"reason": "invalid_or_foreign_folder_id", "folder_id": folder_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pasta não encontrada nesta sessão.",
        )

    total = (
        db.scalar(
            select(func.count(PstMessage.id)).where(
                PstMessage.pst_session_id == pst_sess.id,
                PstMessage.folder_id == folder.id,
            )
        )
        or 0
    )

    order_clauses = {
        "date_desc": [desc(PstMessage.received_at), desc(PstMessage.id)],
        "date_asc": [asc(PstMessage.received_at), asc(PstMessage.id)],
        "sender_asc": [asc(PstMessage.sender_name), asc(PstMessage.sender_email), desc(PstMessage.received_at)],
        "subject_asc": [asc(PstMessage.subject), desc(PstMessage.received_at)],
        "size_desc": [desc(PstMessage.size_bytes), desc(PstMessage.id)],
    }[sort_by]

    offset = (page - 1) * page_size
    stmt = (
        select(
            PstMessage.id,
            PstMessage.folder_id,
            PstMessage.subject,
            PstMessage.sender_name,
            PstMessage.sender_email,
            PstMessage.recipients_to,
            PstMessage.sent_at,
            PstMessage.received_at,
            PstMessage.importance,
            PstMessage.has_attachments,
            PstMessage.attachment_count,
            PstMessage.size_bytes,
            PstMessage.snippet,
        )
        .where(
            PstMessage.pst_session_id == pst_sess.id,
            PstMessage.folder_id == folder.id,
        )
        .order_by(*order_clauses)
        .offset(offset)
        .limit(page_size)
    )
    rows = db.execute(stmt).mappings().all()

    items = [
        {
            "id": r["id"],
            "folder_id": r["folder_id"],
            "subject": r["subject"] or "(Sem assunto)",
            "sender_name": r["sender_name"],
            "sender_email": r["sender_email"],
            "recipients_to": r["recipients_to"],
            "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
            "received_at": r["received_at"].isoformat() if r["received_at"] else None,
            "importance": r["importance"],
            "has_attachments": bool(r["has_attachments"]),
            "attachment_count": r["attachment_count"],
            "size_bytes": r["size_bytes"],
            "snippet": r["snippet"] or "",
        }
        for r in rows
    ]

    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    return {
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "full_path": folder.full_path,
            "folder_role": folder.folder_role,
            "message_count": folder.message_count,
        },
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "sort_by": sort_by,
        "items": items,
    }


def _resolve_inline_cid_images(
    html_sanitized: str | None,
    session_uuid: str,
    attachments: List[PstAttachment],
) -> str | None:
    """
    Restaura todas as imagens do e-mail (externas e internas `cid:`):
      1. Se a mensagem foi extraída anteriormente com `data-blocked-src`, restaura para `src="..."`.
      2. Resolve imagens incorporadas (`data-cid`, `src="cid:..."` ou `alt="[Imagem incorporada: ...]"`)
         convertendo os anexos de imagem da mensagem diretamente para `data:image/...;base64,...`.
    """
    if not html_sanitized:
        return html_sanitized

    # 1. Restaura imagens externas caso tenham sido marcadas como data-blocked-src em extrações anteriores
    restored = re.sub(
        r'\bdata-blocked-src="([^"]+)"',
        r'src="\1"',
        html_sanitized,
        flags=re.IGNORECASE,
    )
    restored = re.sub(
        r'\s*alt="\[Imagem externa bloqueada por segurança\]"',
        "",
        restored,
        flags=re.IGNORECASE,
    )

    session_dir = resolve_session_dir(session_uuid)

    def _att_to_data_uri(att: PstAttachment) -> str | None:
        if not att.storage_rel_path or att.size_bytes > 15 * 1024 * 1024:
            return None
        abs_p = (session_dir / att.storage_rel_path).resolve()
        if not abs_p.is_relative_to(session_dir) or not abs_p.is_file():
            return None
        try:
            b64 = base64.b64encode(abs_p.read_bytes()).decode("ascii")
            return f"data:{att.mime_type};base64,{b64}"
        except Exception:
            return None

    image_atts = [a for a in attachments if (a.mime_type or "").startswith("image/")]
    by_cid: Dict[str, PstAttachment] = {}
    by_filename: Dict[str, PstAttachment] = {}

    for att in image_atts:
        if att.content_id:
            clean_cid = att.content_id.strip("<>").lower()
            by_cid[clean_cid] = att
            if "@" in clean_cid:
                by_cid[clean_cid.split("@", 1)[0]] = att
        if att.original_filename:
            by_filename[att.original_filename.strip().lower()] = att

    used_att_ids = set()

    def _replace_img_tag(match: re.Match) -> str:
        full_tag = match.group(0)

        cid_match = (
            re.search(r'data-cid="([^"]+)"', full_tag, re.IGNORECASE)
            or re.search(r'src="cid:([^"]+)"', full_tag, re.IGNORECASE)
            or re.search(r'alt="\[Imagem incorporada:\s*([^\]]+)\]"', full_tag, re.IGNORECASE)
        )
        if not cid_match:
            return full_tag

        cid_raw = cid_match.group(1).strip()
        cid_key = cid_raw.strip("<>").lower()
        cid_prefix = cid_key.split("@", 1)[0]

        matched_att = by_cid.get(cid_key) or by_cid.get(cid_prefix) or by_filename.get(cid_prefix)

        if matched_att is None:
            for candidate in image_atts:
                if candidate.id not in used_att_ids:
                    matched_att = candidate
                    break

        if matched_att is not None:
            used_att_ids.add(matched_att.id)
            by_cid[cid_key] = matched_att
            data_uri = _att_to_data_uri(matched_att)
            if data_uri:
                # Limpa atributos provisórios e injeta a imagem real em Base64
                tag_clean = re.sub(r'\s*data-cid="[^"]*"', "", full_tag, flags=re.IGNORECASE)
                tag_clean = re.sub(r'\s*src="cid:[^"]*"', "", tag_clean, flags=re.IGNORECASE)
                tag_clean = re.sub(
                    r'\balt="\[Imagem incorporada:[^"]*\]"',
                    f'alt="{matched_att.original_filename}"',
                    tag_clean,
                    flags=re.IGNORECASE,
                )
                return tag_clean.replace("<img", f'<img src="{data_uri}"', 1)

        # Se o e-mail citou um cid: que não veio anexado no PST, oculta a tag quebrada sem poluir o texto
        return ""

    return re.sub(
        r'<img\b[^>]*(?:data-cid=|src="cid:|\[Imagem incorporada:)[^>]*>',
        _replace_img_tag,
        restored,
        flags=re.IGNORECASE,
    )


@router.get("/messages/{message_id}")
def get_message_detail(
    session_uuid: str,
    message_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Retorna os dados completos de uma mensagem selecionada para o Painel de Leitura (Seção 3.4).
    Verifica obrigatoriamente se `message_id` pertence à `pst_session` do usuário autenticado.
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

    msg = db.scalar(
        select(PstMessage).where(
            PstMessage.id == message_id,
            PstMessage.pst_session_id == pst_sess.id,
        )
    )
    if not msg:
        record_audit_event(
            db,
            event_type="AUTHZ_DENIED",
            event_result="FAILURE",
            user_id=auth.user.id,
            username=auth.user.username,
            session_uuid=session_uuid,
            ip_address=auth.ip_address,
            details={"reason": "invalid_or_foreign_message_id", "message_id": message_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mensagem não encontrada nesta sessão.",
        )

    folder = db.get(PstFolder, msg.folder_id)
    atts = list(
        db.scalars(
            select(PstAttachment)
            .where(
                PstAttachment.pst_session_id == pst_sess.id,
                PstAttachment.message_id == msg.id,
            )
            .order_by(PstAttachment.attachment_index.asc())
        ).all()
    )

    resolved_html = _resolve_inline_cid_images(msg.body_html_sanitized, session_uuid, atts)

    # Limpa avisos antigos de bloqueio de imagem externa para não poluir a leitura
    clean_warnings = None
    if msg.extraction_warnings:
        parts = [
            p.strip()
            for p in msg.extraction_warnings.split(";")
            if p.strip()
            and "bloqueado" not in p.lower()
            and "mapi interna" not in p.lower()
        ]
        if parts:
            clean_warnings = "; ".join(parts)

    return {
        "id": msg.id,
        "session_uuid": pst_sess.session_uuid,
        "folder": {
            "id": folder.id if folder else msg.folder_id,
            "name": folder.name if folder else "",
            "full_path": folder.full_path if folder else "",
        },
        "internet_message_id": msg.internet_message_id,
        "subject": msg.subject or "(Sem assunto)",
        "sender_name": msg.sender_name,
        "sender_email": msg.sender_email,
        "recipients_to": msg.recipients_to,
        "recipients_cc": msg.recipients_cc,
        "recipients_bcc": msg.recipients_bcc,
        "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
        "received_at": msg.received_at.isoformat() if msg.received_at else None,
        "importance": msg.importance,
        "size_bytes": msg.size_bytes,
        "has_attachments": msg.has_attachments,
        "attachment_count": msg.attachment_count,
        "body_plain": msg.body_plain,
        "body_html_sanitized": resolved_html,
        "has_transport_headers": bool(msg.transport_headers),
        "transport_headers": msg.transport_headers,
        "extraction_warnings": clean_warnings,
        "attachments": [
            {
                "id": a.id,
                "attachment_index": a.attachment_index,
                "original_filename": a.original_filename,
                "safe_filename": a.safe_filename,
                "mime_type": a.mime_type,
                "size_bytes": a.size_bytes,
                "sha256": a.sha256,
                "extraction_status": a.extraction_status,
                "is_inline": a.is_inline,
                "content_id": a.content_id,
                "has_extracted_text": bool(a.extracted_text),
                "metadata": a.metadata_json,
            }
            for a in atts
        ],
    }

