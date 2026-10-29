"""
Motor de Processamento e Extração de Arquivos PST em Lotes (Fase 3 - Seções 5, 6 e 13).
Combina:
  - `pypff` (libpff) nativo para navegação na árvore MAPI de pastas, mensagens e anexos.
  - Extração de propriedades MAPI estendidas (`record_sets`) + `transport_headers` RFC 5322.
  - Sanitização HTML (`nh3` + bloqueio de imagens externas).
  - Extração e indexação textual de anexos (PDF, DOCX, XLSX, PPTX, TXT, CSV, HTML, RTF, DOC).
  - Abertura progressiva (`READY_PARTIAL` após o primeiro lote) e cancelamento cooperativo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from email.header import decode_header, make_header
from email.parser import HeaderParser
from email.utils import getaddresses, parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from charset_normalizer import from_bytes
from sqlalchemy import select
from sqlalchemy.orm import Session
from striprtf.striprtf import rtf_to_text

from app.core.audit import record_audit_event
from app.database.models import (
    BackgroundJob,
    PstAttachment,
    PstFolder,
    PstMessage,
    PstSession,
)
from app.services.attachment_extractor import (
    detect_mime_and_signature,
    extract_attachment_text_and_metadata,
    sanitize_attachment_filename,
)
from app.services.cleanup_service import execute_session_purge
from app.services.html_sanitizer import (
    html_to_plain_text,
    make_snippet,
    sanitize_email_html,
)
from app.services.session_manager import get_int_setting, resolve_session_dir, utc_now

# Tags MAPI (PidTag*) relevantes para metadados de mensagens e anexos
MAPI_PR_IMPORTANCE = 0x0017
MAPI_PR_SENT_REPRESENTING_EMAIL = 0x0065
MAPI_PR_SENDER_EMAIL = 0x0C1F
MAPI_PR_DISPLAY_BCC = 0x0E02
MAPI_PR_DISPLAY_CC = 0x0E03
MAPI_PR_DISPLAY_TO = 0x0E04
MAPI_PR_INTERNET_MESSAGE_ID = 0x1035
MAPI_PR_DISPLAY_NAME = 0x3001
MAPI_PR_ATTACH_FILENAME = 0x3704
MAPI_PR_ATTACH_LONG_FILENAME = 0x3707
MAPI_PR_ATTACH_MIME_TAG = 0x370E
MAPI_PR_ATTACH_CONTENT_ID = 0x3712
MAPI_PR_ATTACH_CONTENT_LOCATION = 0x3713
MAPI_PR_SENDER_SMTP_ADDRESS = 0x5D01


class JobCancelledError(Exception):
    """Sinaliza que o processamento foi cancelado pelo usuário ou por encerramento da sessão."""


def _safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _clean_db_text(val: Optional[str], max_len: Optional[int] = None) -> Optional[str]:
    """Remove bytes nulos e caracteres surrogate UTF-16 inválidos antes de gravar no MariaDB."""
    if val is None:
        return None
    cleaned = str(val).replace("\x00", "")
    try:
        cleaned.encode("utf-8")
    except UnicodeEncodeError:
        cleaned = cleaned.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    cleaned = cleaned.strip()
    if max_len is not None and len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


def safe_decode_text(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        return _clean_db_text(val)
    if isinstance(val, (bytes, bytearray)):
        raw = bytes(val)
        if not raw:
            return ""
        for enc in ("utf-8", "cp1252", "latin-1", "utf-16-le"):
            try:
                decoded = _clean_db_text(raw.decode(enc))
                if decoded:
                    return decoded
            except UnicodeDecodeError:
                continue
        best = from_bytes(raw).best()
        if best is not None:
            return _clean_db_text(str(best))
        return _clean_db_text(raw.decode("utf-8", errors="replace"))
    return _clean_db_text(str(val))


def decode_mime_header_value(raw_val: Optional[str]) -> Optional[str]:
    if not raw_val:
        return None
    try:
        return str(make_header(decode_header(raw_val))).strip()
    except Exception:
        return raw_val.strip()


def classify_folder_role(folder_name: str, depth: int) -> str:
    """Identifica o papel da pasta para organização visual semelhante ao Outlook."""
    norm = folder_name.strip().lower()
    if norm in ("caixa de entrada", "inbox", "entrada", "recebidos", "recebidas"):
        return "INBOX"
    if norm in ("itens enviados", "sent items", "sent", "enviados", "enviadas"):
        return "SENT"
    if norm in ("rascunhos", "drafts"):
        return "DRAFTS"
    if norm in ("itens excluídos", "itens excluidos", "deleted items", "trash", "lixeira"):
        return "TRASH"
    if norm in ("arquivo", "archive", "arquivo morto"):
        return "ARCHIVE"
    if norm in ("lixo eletrônico", "lixo eletronico", "junk", "junk e-mail", "junk email", "spam"):
        return "JUNK"
    return "CUSTOM"


def folder_role_sort_priority(role: str) -> int:
    order = {
        "INBOX": 1,
        "DRAFTS": 2,
        "SENT": 3,
        "ARCHIVE": 4,
        "JUNK": 5,
        "TRASH": 6,
        "CUSTOM": 10,
    }
    return order.get(role, 10)


def extract_mapi_properties(item: Any) -> Dict[int, Any]:
    """Extrai propriedades MAPI de `item.record_sets` de forma resiliente."""
    props: Dict[int, Any] = {}
    num_sets = _safe_getattr(item, "number_of_record_sets", 0) or 0
    for s_idx in range(num_sets):
        try:
            rset = item.get_record_set(s_idx)
            num_entries = _safe_getattr(rset, "number_of_entries", 0) or 0
            for e_idx in range(num_entries):
                try:
                    entry = rset.get_entry(e_idx)
                    etag = _safe_getattr(entry, "entry_type", None)
                    if etag is None or etag in props:
                        continue
                    str_val = _safe_getattr(entry, "data_as_string", None)
                    if str_val is not None:
                        props[etag] = safe_decode_text(str_val)
                        continue
                    int_val = _safe_getattr(entry, "data_as_integer", None)
                    if int_val is not None:
                        props[etag] = int_val
                        continue
                    raw_data = _safe_getattr(entry, "data", None)
                    if raw_data is not None:
                        vtype = _safe_getattr(entry, "value_type", None)
                        if vtype == 0x001F and isinstance(raw_data, (bytes, bytearray)):
                            try:
                                props[etag] = bytes(raw_data).decode("utf-16-le", errors="replace").replace("\x00", "").strip()
                                continue
                            except Exception:
                                pass
                        props[etag] = safe_decode_text(raw_data)
                except Exception:
                    continue
        except Exception:
            continue
    return props


def parse_transport_headers(raw_headers: Optional[str]) -> Dict[str, Any]:
    """Analisa cabeçalhos RFC 5322 (`transport_headers`) quando disponíveis."""
    if not raw_headers:
        return {}
    try:
        msg_hdr = HeaderParser().parsestr(raw_headers)
    except Exception:
        return {}

    result: Dict[str, Any] = {}
    if msg_hdr.get("Subject"):
        result["subject"] = decode_mime_header_value(msg_hdr.get("Subject"))
    if msg_hdr.get("Message-ID"):
        result["message_id"] = msg_hdr.get("Message-ID", "").strip()[:255]

    from_vals = msg_hdr.get_all("From", [])
    if from_vals:
        parsed_from = getaddresses([decode_mime_header_value(v) or v for v in from_vals])
        if parsed_from:
            disp_name, addr = parsed_from[0]
            if disp_name:
                result["sender_name"] = disp_name.strip()[:255]
            if addr:
                result["sender_email"] = addr.strip()[:320]

    for field_name, key_name in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
        vals = msg_hdr.get_all(field_name, [])
        if vals:
            addrs = getaddresses([decode_mime_header_value(v) or v for v in vals])
            formatted = []
            for name, addr in addrs:
                if name and addr:
                    formatted.append(f"{name} <{addr}>")
                elif addr:
                    formatted.append(addr)
                elif name:
                    formatted.append(name)
            if formatted:
                result[key_name] = ", ".join(formatted)

    if msg_hdr.get("Date"):
        try:
            dt = parsedate_to_datetime(msg_hdr.get("Date"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            if 1900 <= dt.year <= 2100:
                result["date"] = dt
        except Exception:
            pass

    imp = (msg_hdr.get("Importance") or msg_hdr.get("X-Priority") or "").strip().lower()
    if imp in ("high", "1", "2", "alta"):
        result["importance"] = 2
    elif imp in ("low", "4", "5", "baixa"):
        result["importance"] = 0

    return result


def _normalize_datetime(dt_val: Any) -> Optional[datetime]:
    if not isinstance(dt_val, datetime):
        return None
    if dt_val.tzinfo is not None:
        dt_val = dt_val.astimezone(timezone.utc).replace(tzinfo=None)
    if not (1900 <= dt_val.year <= 2100):
        return None
    return dt_val


def _check_if_cancelled(db: Session, job_id: int, pst_session_id: int) -> None:
    """
    Verifica diretamente no MariaDB se o job foi cancelado ou a sessão encerrada,
    sem chamar `db.expire_all()` para nunca descartar objetos pendentes na memória.
    """
    job_row = db.execute(
        select(BackgroundJob.cancel_requested, BackgroundJob.status).where(
            BackgroundJob.id == job_id
        )
    ).first()
    sess_row = db.execute(
        select(PstSession.status).where(PstSession.id == pst_session_id)
    ).first()
    if not job_row or not sess_row:
        raise JobCancelledError("Sessão ou job não existe mais.")
    if job_row[0] or job_row[1] == "CANCELLED":
        raise JobCancelledError("Cancelamento solicitado pelo usuário.")
    if sess_row[0] in ("CANCELLED", "CLOSING", "CLEANING", "PURGED"):
        raise JobCancelledError(f"Sessão em encerramento ({sess_row[0]}).")


def _count_tree_items(folder: Any) -> Tuple[int, int]:
    """Retorna (total_pastas, total_mensagens) na árvore PFF para barra de progresso precisa."""
    total_f = 0
    total_m = 0
    n_msgs = _safe_getattr(folder, "number_of_sub_messages", 0) or 0
    n_subs = _safe_getattr(folder, "number_of_sub_folders", 0) or 0
    name = safe_decode_text(_safe_getattr(folder, "name", None))
    if name or n_msgs > 0:
        total_f += 1
        total_m += n_msgs
    for i in range(n_subs):
        sub = _safe_getattr(folder, "get_sub_folder", lambda _: None)(i)
        if sub is not None:
            sf, sm = _count_tree_items(sub)
            total_f += sf
            total_m += sm
    return total_f, total_m


def process_pst_extraction_job(db: Session, job_id: int) -> Dict[str, Any]:
    """
    Executa a extração completa de um arquivo PST associado a `job_id`.
    """
    import pypff  # type: ignore

    job = db.get(BackgroundJob, job_id)
    if not job:
        raise RuntimeError(f"Job {job_id} não encontrado.")
    pst_session = db.get(PstSession, job.pst_session_id)
    if not pst_session:
        raise RuntimeError(f"Sessão PST {job.pst_session_id} não encontrada.")

    now = utc_now()
    job.status = "RUNNING"
    job.worker_pid = os.getpid()
    job.started_at = now
    job.attempts += 1

    pst_session.status = "PROCESSING"
    pst_session.current_stage = "Iniciando leitura da estrutura de pastas do PST"
    db.commit()

    session_dir = resolve_session_dir(pst_session.session_uuid)
    pst_file_path = session_dir / "original.pst"
    attachments_dir = session_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    batch_size = min(get_int_setting(db, "batch_commit_size", 10), 15)
    idle_timeout_min = get_int_setting(db, "session_idle_timeout_minutes", 30)
    max_session_disk_mb = get_int_setting(db, "max_session_disk_mb", 12288)
    max_session_disk_bytes = max_session_disk_mb * 1024 * 1024
    max_att_extract_mb = get_int_setting(db, "max_attachment_extract_mb", 50)
    enable_ocr = bool(get_int_setting(db, "enable_ocr_tesseract", 0))

    diagnostics: Dict[str, Any] = {
        "engine": f"pypff {pypff.get_version()}",
        "corrupted_messages": 0,
        "corrupted_attachments": 0,
        "encrypted_attachments": 0,
        "rtf_only_messages": 0,
        "external_resources_blocked": 0,
        "warnings": [],
    }

    pff = pypff.file()
    try:
        pff.open(str(pst_file_path))
        root_folder = pff.get_root_folder()
        if not root_folder:
            raise RuntimeError("Não foi possível localizar a pasta raiz no arquivo PST.")

        total_folders_est, total_msgs_est = _count_tree_items(root_folder)
        pst_session.total_folders = max(total_folders_est, 1)
        pst_session.total_messages = total_msgs_est
        pst_session.current_stage = (
            f"Mapeando {pst_session.total_folders} pastas e {total_msgs_est} mensagens"
        )
        db.commit()

        uncommitted_msgs = 0
        batch_orm_objects: List[Any] = []

        def _commit_and_free_batch(stage_text: str) -> None:
            nonlocal uncommitted_msgs
            from datetime import timedelta

            _update_progress(stage_text)
            now_commit = utc_now()
            pst_session.last_heartbeat_at = now_commit
            pst_session.idle_expires_at = now_commit + timedelta(minutes=idle_timeout_min)
            pst_session.diagnostic_summary = json.dumps(diagnostics, ensure_ascii=False)
            db.commit()
            for obj in batch_orm_objects:
                try:
                    if obj in db:
                        db.expunge(obj)
                except Exception:
                    pass
            batch_orm_objects.clear()
            uncommitted_msgs = 0

        def _update_progress(stage_text: str) -> None:
            if pst_session.total_messages > 0:
                pct = min(
                    99.0,
                    round(
                        (pst_session.processed_messages / pst_session.total_messages) * 100.0,
                        2,
                    ),
                )
            else:
                pct = min(
                    99.0,
                    round(
                        (pst_session.processed_folders / max(pst_session.total_folders, 1))
                        * 100.0,
                        2,
                    ),
                )
            pst_session.progress_percent = Decimal(str(pct))
            pst_session.current_stage = stage_text[:120]
            # Assim que houver ao menos 1 pasta processada, libera abertura progressiva (READY_PARTIAL)
            if pst_session.status == "PROCESSING" and pst_session.processed_folders >= 1:
                pst_session.status = "READY_PARTIAL"

        def _walk_and_extract(
            pff_folder: Any,
            parent_db_id: Optional[int],
            parent_path: str,
            depth: int,
            sibling_idx: int,
        ) -> None:
            nonlocal uncommitted_msgs
            _check_if_cancelled(db, job.id, pst_session.id)

            raw_name = safe_decode_text(_safe_getattr(pff_folder, "name", None))
            num_msgs = _safe_getattr(pff_folder, "number_of_sub_messages", 0) or 0
            num_subs = _safe_getattr(pff_folder, "number_of_sub_folders", 0) or 0

            db_folder: Optional[PstFolder] = None
            folder_db_id: Optional[int] = None
            folder_display_name: str = raw_name or "Raiz do PST"
            current_path = parent_path

            # Se for pasta real (com nome ou mensagens), cria registro em pst_folders
            if depth > 0 or raw_name or num_msgs > 0:
                folder_name = raw_name or "Raiz do PST"
                folder_display_name = folder_name
                current_path = f"{parent_path}/{folder_name}" if parent_path else f"/{folder_name}"
                role = classify_folder_role(folder_name, depth)
                sort_ord = folder_role_sort_priority(role) * 1000 + sibling_idx
                pff_id = _safe_getattr(pff_folder, "identifier", None)

                db_folder = PstFolder(
                    pst_session_id=pst_session.id,
                    parent_folder_id=parent_db_id,
                    pff_identifier=_clean_db_text(str(pff_id) if pff_id is not None else None, 64),
                    name=_clean_db_text(folder_name, 255) or "Pasta",
                    full_path=_clean_db_text(current_path, 1024) or "/Pasta",
                    folder_role=role,
                    depth=max(0, depth - 1),
                    message_count=num_msgs,
                    unread_count=0,
                    sort_order=sort_ord,
                )
                db.add(db_folder)
                db.flush()
                folder_db_id = db_folder.id

                pst_session.processed_folders += 1
                _commit_and_free_batch(f"Processando pasta: {folder_name}")

            # Extrai mensagens da pasta atual em lotes isolados com SAVEPOINT
            if folder_db_id is not None and num_msgs > 0:
                for m_idx in range(num_msgs):
                    if m_idx % 10 == 0:
                        _check_if_cancelled(db, job.id, pst_session.id)

                    try:
                        pff_msg = pff_folder.get_sub_message(m_idx)
                        with db.begin_nested():
                            _extract_single_message(pff_msg, folder_db_id, m_idx)
                    except JobCancelledError:
                        raise
                    except Exception as exc:
                        pst_session.corrupted_items += 1
                        diagnostics["corrupted_messages"] += 1
                        if len(diagnostics["warnings"]) < 50:
                            diagnostics["warnings"].append(
                                f"Mensagem corrompida na pasta '{folder_display_name}' (#{m_idx + 1}): {str(exc)[:120]}"
                            )

                    pst_session.processed_messages += 1
                    uncommitted_msgs += 1

                    if m_idx == 0 or uncommitted_msgs >= batch_size:
                        _commit_and_free_batch(
                            f"Extraindo '{folder_display_name}' ({pst_session.processed_messages}/{pst_session.total_messages})"
                        )

                if uncommitted_msgs > 0:
                    _commit_and_free_batch(f"Pasta concluída: {folder_display_name}")

            # Percorre subpastas recursivamente
            next_parent_id = folder_db_id if folder_db_id is not None else parent_db_id
            for s_idx in range(num_subs):
                try:
                    sub_f = pff_folder.get_sub_folder(s_idx)
                    if sub_f is not None:
                        _walk_and_extract(
                            sub_f,
                            parent_db_id=next_parent_id,
                            parent_path=current_path,
                            depth=depth + 1,
                            sibling_idx=s_idx,
                        )
                except JobCancelledError:
                    raise
                except Exception as exc:
                    pst_session.corrupted_items += 1
                    if len(diagnostics["warnings"]) < 50:
                        diagnostics["warnings"].append(
                            f"Subpasta ilegível em '{current_path}': {str(exc)[:120]}"
                        )

        def _extract_single_message(pff_msg: Any, folder_db_id: int, msg_idx: int) -> None:
            mapi_props = extract_mapi_properties(pff_msg)
            raw_headers = _clean_db_text(
                safe_decode_text(_safe_getattr(pff_msg, "transport_headers", None)),
                60000,
            )
            hdr_info = parse_transport_headers(raw_headers)

            subject = _clean_db_text(
                safe_decode_text(_safe_getattr(pff_msg, "subject", None))
                or hdr_info.get("subject")
                or "(Sem assunto)",
                998,
            )

            sender_name = _clean_db_text(
                safe_decode_text(_safe_getattr(pff_msg, "sender_name", None))
                or hdr_info.get("sender_name")
                or mapi_props.get(MAPI_PR_DISPLAY_NAME),
                255,
            )

            sender_email = _clean_db_text(
                hdr_info.get("sender_email")
                or mapi_props.get(MAPI_PR_SENDER_SMTP_ADDRESS)
                or mapi_props.get(MAPI_PR_SENDER_EMAIL)
                or mapi_props.get(MAPI_PR_SENT_REPRESENTING_EMAIL),
                320,
            )

            recipients_to = _clean_db_text(
                hdr_info.get("to") or mapi_props.get(MAPI_PR_DISPLAY_TO), 60000
            )
            recipients_cc = _clean_db_text(
                hdr_info.get("cc") or mapi_props.get(MAPI_PR_DISPLAY_CC), 60000
            )
            recipients_bcc = _clean_db_text(
                hdr_info.get("bcc") or mapi_props.get(MAPI_PR_DISPLAY_BCC), 60000
            )

            internet_msg_id = _clean_db_text(
                hdr_info.get("message_id") or mapi_props.get(MAPI_PR_INTERNET_MESSAGE_ID),
                255,
            )

            delivery_dt = _normalize_datetime(_safe_getattr(pff_msg, "delivery_time", None))
            submit_dt = _normalize_datetime(_safe_getattr(pff_msg, "client_submit_time", None))
            hdr_dt = hdr_info.get("date")

            received_at = delivery_dt or hdr_dt or submit_dt
            sent_at = submit_dt or hdr_dt or delivery_dt

            importance = hdr_info.get("importance")
            if importance is None:
                mapi_imp = mapi_props.get(MAPI_PR_IMPORTANCE)
                if mapi_imp in (0, 1, 2):
                    importance = int(mapi_imp)
                else:
                    importance = 1

            plain_body = _clean_db_text(
                safe_decode_text(_safe_getattr(pff_msg, "plain_text_body", None)),
                15_000_000,
            )
            raw_html = safe_decode_text(_safe_getattr(pff_msg, "html_body", None))
            raw_rtf = safe_decode_text(_safe_getattr(pff_msg, "rtf_body", None))

            msg_warnings: List[str] = []
            sanitized_html: Optional[str] = None

            if raw_html:
                sanitized_html, _ = sanitize_email_html(raw_html)
                sanitized_html = _clean_db_text(sanitized_html, 15_000_000)
                if not plain_body:
                    plain_body = _clean_db_text(html_to_plain_text(sanitized_html), 15_000_000)

            elif not plain_body and raw_rtf:
                diagnostics["rtf_only_messages"] += 1
                try:
                    plain_body = _clean_db_text(rtf_to_text(raw_rtf).strip(), 15_000_000)
                except Exception:
                    pass

            num_att = _safe_getattr(pff_msg, "number_of_attachments", 0) or 0
            pst_session.total_attachments += num_att

            body_len = len((plain_body or "").encode("utf-8")) + len(
                (sanitized_html or "").encode("utf-8")
            )
            pff_msg_id = _safe_getattr(pff_msg, "identifier", None)

            db_msg = PstMessage(
                pst_session_id=pst_session.id,
                folder_id=folder_db_id,
                pff_message_id=_clean_db_text(
                    str(pff_msg_id) if pff_msg_id is not None else str(msg_idx), 64
                ),
                internet_message_id=internet_msg_id,
                subject=subject,
                sender_name=sender_name,
                sender_email=sender_email,
                recipients_to=recipients_to,
                recipients_cc=recipients_cc,
                recipients_bcc=recipients_bcc,
                sent_at=sent_at,
                received_at=received_at,
                importance=importance,
                has_attachments=(num_att > 0),
                attachment_count=min(num_att, 30000),
                size_bytes=min(body_len, 2_000_000_000),
                snippet=_clean_db_text(make_snippet(plain_body), 300),
                body_plain=plain_body,
                body_html_sanitized=sanitized_html,
                transport_headers=raw_headers,
                extraction_warnings=(
                    _clean_db_text("; ".join(msg_warnings), 500) if msg_warnings else None
                ),
            )
            db.add(db_msg)
            db.flush()
            batch_orm_objects.append(db_msg)

            # Extração de anexos da mensagem (cada anexo em seu próprio SAVEPOINT)
            for a_idx in range(num_att):
                try:
                    pff_att = pff_msg.get_attachment(a_idx)
                    with db.begin_nested():
                        _extract_single_attachment(pff_att, db_msg, a_idx)
                except Exception as exc:
                    pst_session.corrupted_items += 1
                    diagnostics["corrupted_attachments"] += 1
                    if len(diagnostics["warnings"]) < 50:
                        diagnostics["warnings"].append(
                            f"Anexo #{a_idx + 1} ilegível na mensagem ID {db_msg.id}: {str(exc)[:100]}"
                        )
                pst_session.processed_attachments += 1

        def _extract_single_attachment(
            pff_att: Any, db_msg: PstMessage, att_idx: int
        ) -> None:
            att_props = extract_mapi_properties(pff_att)
            raw_fname = (
                safe_decode_text(_safe_getattr(pff_att, "name", None))
                or att_props.get(MAPI_PR_ATTACH_LONG_FILENAME)
                or att_props.get(MAPI_PR_ATTACH_FILENAME)
                or att_props.get(MAPI_PR_DISPLAY_NAME)
                or f"anexo_{att_idx + 1}.bin"
            )
            safe_fname = sanitize_attachment_filename(str(raw_fname), default_index=att_idx + 1)

            att_size = _safe_getattr(pff_att, "size", 0) or 0
            if pst_session.disk_usage_bytes + att_size > max_session_disk_bytes:
                db_att = PstAttachment(
                    pst_session_id=pst_session.id,
                    message_id=db_msg.id,
                    attachment_index=att_idx,
                    original_filename=_clean_db_text(str(raw_fname), 255) or safe_fname,
                    safe_filename=safe_fname,
                    mime_type="application/octet-stream",
                    size_bytes=att_size,
                    storage_rel_path="",
                    extraction_status="SIZE_LIMIT_EXCEEDED",
                    metadata_json={"reason": "session_disk_quota_exceeded"},
                )
                db.add(db_att)
                db.flush()
                batch_orm_objects.append(db_att)
                return

            rel_path = f"attachments/msg_{db_msg.id}_att_{att_idx}_{safe_fname}"
            abs_att_path = session_dir / rel_path

            hasher = hashlib.sha256()
            written = 0
            pff_att.seek_offset(0, os.SEEK_SET)
            with abs_att_path.open("wb") as af:
                os.chmod(abs_att_path, 0o600)
                remaining = att_size
                while remaining > 0:
                    chunk_len = min(remaining, 1024 * 1024)
                    buf = pff_att.read_buffer(chunk_len)
                    if not buf:
                        break
                    af.write(buf)
                    hasher.update(buf)
                    written += len(buf)
                    remaining -= len(buf)

            pst_session.disk_usage_bytes += written
            db_msg.size_bytes = min(db_msg.size_bytes + written, 2_000_000_000)

            detected_mime = detect_mime_and_signature(abs_att_path, safe_fname)
            content_id = (
                att_props.get(MAPI_PR_ATTACH_CONTENT_ID)
                or att_props.get(MAPI_PR_ATTACH_CONTENT_LOCATION)
            )
            if content_id:
                content_id = _clean_db_text(str(content_id).strip("<>"), 255)

            ext_status, ext_text, ext_meta = extract_attachment_text_and_metadata(
                file_path=abs_att_path,
                filename=safe_fname,
                mime_type=detected_mime,
                max_extract_mb=max_att_extract_mb,
                enable_ocr=enable_ocr,
            )
            if ext_status == "ENCRYPTED_OR_PASSWORD":
                diagnostics["encrypted_attachments"] += 1

            db_att = PstAttachment(
                pst_session_id=pst_session.id,
                message_id=db_msg.id,
                attachment_index=att_idx,
                original_filename=_clean_db_text(str(raw_fname), 255) or safe_fname,
                safe_filename=safe_fname,
                mime_type=_clean_db_text(detected_mime, 127) or "application/octet-stream",
                size_bytes=written,
                sha256=hasher.hexdigest(),
                storage_rel_path=_clean_db_text(rel_path, 255) or safe_fname,
                extraction_status=ext_status,
                is_inline=bool(content_id),
                content_id=content_id,
                extracted_text=_clean_db_text(ext_text, 15_000_000),
                metadata_json=ext_meta,
            )
            db.add(db_att)
            db.flush()
            batch_orm_objects.append(db_att)

        _walk_and_extract(
            root_folder,
            parent_db_id=None,
            parent_path="",
            depth=0,
            sibling_idx=0,
        )

        # Finalização com sucesso
        finished_now = utc_now()
        pst_session.status = "READY"
        pst_session.progress_percent = Decimal("100.00")
        pst_session.current_stage = "Processamento e indexação concluídos"
        pst_session.diagnostic_summary = json.dumps(diagnostics, ensure_ascii=False)

        job.status = "COMPLETED"
        job.finished_at = finished_now
        db.commit()

        record_audit_event(
            db,
            event_type="EXTRACT_DONE",
            event_result="SUCCESS",
            user_id=pst_session.user_id,
            session_uuid=pst_session.session_uuid,
            details={
                "folders": pst_session.processed_folders,
                "messages": pst_session.processed_messages,
                "attachments": pst_session.processed_attachments,
                "corrupted_items": pst_session.corrupted_items,
            },
        )
        return {
            "session_uuid": pst_session.session_uuid,
            "status": pst_session.status,
            "folders": pst_session.processed_folders,
            "messages": pst_session.processed_messages,
            "attachments": pst_session.processed_attachments,
            "diagnostics": diagnostics,
        }

    except JobCancelledError as cancel_exc:
        try:
            pff.close()
        except Exception:
            pass
        db.rollback()
        pst_session = db.get(PstSession, pst_session.id)
        job = db.get(BackgroundJob, job.id)
        if job:
            job.status = "CANCELLED"
            job.finished_at = utc_now()
            job.last_error = str(cancel_exc)
            db.commit()
        if pst_session and pst_session.status != "PURGED":
            execute_session_purge(
                db,
                pst_session=pst_session,
                reason="EXTRACTION_CANCELLED_BY_USER",
                actor_user_id=pst_session.user_id,
            )
        return {
            "session_uuid": pst_session.session_uuid if pst_session else None,
            "status": "CANCELLED_AND_PURGED",
            "reason": str(cancel_exc),
        }

    except Exception as exc:
        try:
            pff.close()
        except Exception:
            pass
        db.rollback()
        err_msg = str(exc)[:500]
        pst_session = db.get(PstSession, pst_session.id)
        job = db.get(BackgroundJob, job.id)
        if job:
            job.status = "FAILED"
            job.finished_at = utc_now()
            job.last_error = err_msg
        if pst_session:
            pst_session.status = "FAILED"
            pst_session.current_stage = f"Falha na extração: {err_msg[:90]}"
            diagnostics["fatal_error"] = err_msg
            pst_session.diagnostic_summary = json.dumps(diagnostics, ensure_ascii=False)
        db.commit()

        record_audit_event(
            db,
            event_type="EXTRACT_FAIL",
            event_result="FAILURE",
            user_id=pst_session.user_id if pst_session else None,
            session_uuid=pst_session.session_uuid if pst_session else None,
            details={"error": err_msg},
        )
        raise

    finally:
        try:
            pff.close()
        except Exception:
            pass


def request_session_extraction_cancel(
    db: Session,
    session_uuid: str,
    user_id: int,
    username: str,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Solicita o cancelamento de um processamento PST em andamento ou na fila
    e remove os arquivos parciais quando o job ainda não iniciou no worker.
    """
    from app.services.session_manager import get_owned_pst_session

    pst_sess = get_owned_pst_session(
        db,
        session_uuid=session_uuid,
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        require_readable=False,
        touch_heartbeat=False,
    )
    now = utc_now()
    pst_sess.status = "CANCELLED"
    pst_sess.current_stage = "Cancelamento solicitado pelo usuário"

    running_job = None
    for j in pst_sess.jobs:
        if j.job_type == "EXTRACT_PST" and j.status in ("PENDING", "RUNNING"):
            j.cancel_requested = True
            if j.status == "PENDING":
                j.status = "CANCELLED"
                j.finished_at = now
            else:
                running_job = j
    db.commit()

    # Se não estava em execução ativa no worker, expurga imediatamente
    if running_job is None:
        purge_info = execute_session_purge(
            db,
            pst_session=pst_sess,
            reason="CANCELLED_BEFORE_WORKER_EXEC",
            actor_user_id=user_id,
            actor_username=username,
            ip_address=ip_address,
        )
        return {"cancelled": True, "immediate_purge": True, "purge_info": purge_info}

    return {
        "cancelled": True,
        "immediate_purge": False,
        "message": "Sinal de cancelamento enviado ao worker; arquivos parciais serão eliminados em instantes.",
    }

