"""
Rotas de Impressão e Exportação Individual de Mensagens em EML e TXT (Seção 7):
  - Exportação EML RFC 5322 com preservação de cabeçalhos/anexos (GET .../messages/{id}/export.eml)
  - Exportação TXT estruturada (GET .../messages/{id}/export.txt)
  - Versão dedicada para Impressão de E-mail com CSS @media print (GET .../messages/{id}/print)
  - Impressão separada de Anexo compatível (GET .../attachments/{att_id}/print)
"""

from __future__ import annotations

import email.policy
from email.message import EmailMessage
from email.parser import HeaderParser
from email.utils import format_datetime
from datetime import timezone
import html
import re
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_auth
from app.auth.security import AuthorizationError
from app.core.audit import record_audit_event
from app.database.models import PstAttachment, PstFolder, PstMessage
from app.database.session import get_db
from app.services.session_manager import get_owned_pst_session, resolve_session_dir

router = APIRouter(prefix="/api/sessions/{session_uuid}", tags=["export_and_print"])

SAFE_EXPORT_NAME_RE = re.compile(r"[^a-zA-Z0-9._\-À-ÿ]")


def sanitize_export_filename(subject: str | None, msg_id: int, ext: str) -> str:
    raw = (subject or f"mensagem_{msg_id}").strip()
    cleaned = SAFE_EXPORT_NAME_RE.sub("_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    if not cleaned:
        cleaned = f"mensagem_{msg_id}"
    return f"{cleaned[:80]}_{msg_id}.{ext.lstrip('.')}"


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def build_rfc5322_eml_bytes(
    msg: PstMessage,
    attachments: List[PstAttachment],
    session_dir,
) -> tuple[bytes, bool]:
    """
    Gera um arquivo .eml RFC 5322 válido contendo cabeçalhos, corpo texto/HTML e anexos incorporados.
    Retorna (eml_bytes, is_reconstructed).
    """
    eml = EmailMessage(policy=email.policy.SMTP)
    is_reconstructed = not bool(msg.transport_headers and msg.transport_headers.strip())

    preserved_headers = set()
    if not is_reconstructed and msg.transport_headers:
        try:
            parsed_hdrs = HeaderParser().parsestr(msg.transport_headers)
            # Preserva cabeçalhos informativos e de rastreio originais (exceto Content-Type/Boundary que serão montados pelo EmailMessage)
            skip_hdrs = {
                "content-type",
                "content-transfer-encoding",
                "mime-version",
            }
            for k, v in parsed_hdrs.items():
                kl = k.lower()
                if kl in skip_hdrs or kl in preserved_headers:
                    continue
                try:
                    clean_v = " ".join(str(v).splitlines()).strip()
                    if clean_v:
                        eml[k] = clean_v
                        preserved_headers.add(kl)
                except Exception:
                    continue
        except Exception:
            is_reconstructed = True

    if "subject" not in preserved_headers:
        eml["Subject"] = msg.subject or "(Sem assunto)"

    if "from" not in preserved_headers:
        if msg.sender_name and msg.sender_email:
            eml["From"] = f"{msg.sender_name} <{msg.sender_email}>"
        elif msg.sender_email:
            eml["From"] = msg.sender_email
        elif msg.sender_name:
            eml["From"] = f"{msg.sender_name} <remetente.mapi@local.invalid>"
        else:
            eml["From"] = "desconhecido@local.invalid"

    if "to" not in preserved_headers and msg.recipients_to:
        eml["To"] = " ".join(msg.recipients_to.splitlines())

    if "cc" not in preserved_headers and msg.recipients_cc:
        eml["Cc"] = " ".join(msg.recipients_cc.splitlines())

    if "bcc" not in preserved_headers and msg.recipients_bcc:
        eml["Bcc"] = " ".join(msg.recipients_bcc.splitlines())

    if "date" not in preserved_headers:
        dt = msg.received_at or msg.sent_at
        if dt:
            eml["Date"] = format_datetime(dt.replace(tzinfo=timezone.utc))

    if "message-id" not in preserved_headers and msg.internet_message_id:
        eml["Message-ID"] = msg.internet_message_id

    if is_reconstructed:
        eml["X-PSTViewer-Reconstructed"] = "true"
        eml["X-PSTViewer-Note"] = (
            "Mensagem reconstruida a partir das propriedades MAPI extraidas do arquivo PST."
        )
    else:
        eml["X-PSTViewer-Reconstructed"] = "false"

    plain_body = msg.body_plain or ""
    html_body = msg.body_html_sanitized or ""

    if plain_body and html_body:
        eml.set_content(plain_body)
        eml.add_alternative(html_body, subtype="html")
    elif html_body:
        eml.set_content("Mensagem em formato HTML.", subtype="plain")
        eml.add_alternative(html_body, subtype="html")
    else:
        eml.set_content(plain_body or "(Mensagem sem corpo textual)")

    for att in attachments:
        if not att.storage_rel_path:
            continue
        abs_att = (session_dir / att.storage_rel_path).resolve()
        if not abs_att.is_relative_to(session_dir) or not abs_att.is_file():
            continue
        raw_bytes = abs_att.read_bytes()
        mime_parts = (att.mime_type or "application/octet-stream").split("/", 1)
        maintype = mime_parts[0] if len(mime_parts) == 2 else "application"
        subtype = mime_parts[1] if len(mime_parts) == 2 else "octet-stream"

        cid = f"<{att.content_id.strip('<>')}>" if att.content_id else None
        eml.add_attachment(
            raw_bytes,
            maintype=maintype,
            subtype=subtype,
            filename=att.original_filename or att.safe_filename,
            cid=cid,
        )

    return eml.as_bytes(), is_reconstructed


def _load_owned_message_and_attachments(
    db: Session,
    session_uuid: str,
    message_id: int,
    auth: AuthContext,
):
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
            details={"reason": "invalid_or_foreign_message_id_export", "message_id": message_id},
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
    session_dir = resolve_session_dir(pst_sess.session_uuid)
    return pst_sess, folder, msg, atts, session_dir


@router.get("/messages/{message_id}/export.eml")
def export_message_eml(
    session_uuid: str,
    message_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Gera e transfere diretamente ao navegador do usuário um arquivo .eml válido (Seção 7.2).
    """
    pst_sess, _, msg, atts, session_dir = _load_owned_message_and_attachments(
        db, session_uuid, message_id, auth
    )
    eml_bytes, is_reconstructed = build_rfc5322_eml_bytes(msg, atts, session_dir)
    filename = sanitize_export_filename(msg.subject, msg.id, "eml")
    encoded_name = quote(filename)

    record_audit_event(
        db,
        event_type="EXPORT_EML",
        event_result="SUCCESS",
        user_id=auth.user.id,
        username=auth.user.username,
        session_uuid=pst_sess.session_uuid,
        ip_address=auth.ip_address,
        details={
            "message_id": msg.id,
            "reconstructed": is_reconstructed,
            "attachments_included": len(atts),
            "eml_size_bytes": len(eml_bytes),
        },
    )

    return Response(
        content=eml_bytes,
        media_type="message/rfc822",
        headers={
            "X-Content-Type-Options": "nosniff",
            "X-PSTViewer-Reconstructed": "true" if is_reconstructed else "false",
            "Cache-Control": "private, no-store, max-age=0",
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_name}",
        },
    )


@router.get("/messages/{message_id}/export.txt")
def export_message_txt(
    session_uuid: str,
    message_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Exporta a mensagem em formato texto estruturado (.txt) com cabeçalhos e lista de anexos (Seção 7.3).
    """
    pst_sess, folder, msg, atts, _ = _load_owned_message_and_attachments(
        db, session_uuid, message_id, auth
    )
    filename = sanitize_export_filename(msg.subject, msg.id, "txt")
    encoded_name = quote(filename)

    dt_str = (
        (msg.received_at or msg.sent_at).strftime("%d/%m/%Y %H:%M:%S UTC")
        if (msg.received_at or msg.sent_at)
        else "Não informada"
    )
    sender_str = (
        f"{msg.sender_name} <{msg.sender_email}>"
        if (msg.sender_name and msg.sender_email)
        else (msg.sender_name or msg.sender_email or "Não informado")
    )

    lines = [
        "========================================================================",
        f"PST VIEWER - EXPORTAÇÃO DE MENSAGEM (#{msg.id})",
        "========================================================================",
        f"Pasta:        {folder.full_path if folder else ''}",
        f"Assunto:      {msg.subject or '(Sem assunto)'}",
        f"De:           {sender_str}",
        f"Para:         {msg.recipients_to or '-'}",
    ]
    if msg.recipients_cc:
        lines.append(f"CC:           {msg.recipients_cc}")
    if msg.recipients_bcc:
        lines.append(f"CCO:          {msg.recipients_bcc}")
    lines.append(f"Data/Hora:    {dt_str}")
    if msg.extraction_warnings:
        lines.append(f"Observações:  {msg.extraction_warnings}")

    lines.append("\n--- RELAÇÃO DE ANEXOS ---")
    if atts:
        for idx, a in enumerate(atts, start=1):
            lines.append(
                f"  {idx}. {a.original_filename} ({_format_size(a.size_bytes)}, {a.mime_type}) [SHA-256: {a.sha256 or 'N/A'}]"
            )
    else:
        lines.append("  (Sem anexos)")

    lines.append("\n--- CORPO DA MENSAGEM ---\n")
    lines.append(msg.body_plain or "(Corpo textual vazio)")
    lines.append("\n========================================================================")

    txt_bytes = "\n".join(lines).encode("utf-8")

    record_audit_event(
        db,
        event_type="EXPORT_TXT",
        event_result="SUCCESS",
        user_id=auth.user.id,
        username=auth.user.username,
        session_uuid=pst_sess.session_uuid,
        ip_address=auth.ip_address,
        details={"message_id": msg.id, "size_bytes": len(txt_bytes)},
    )

    return Response(
        content=txt_bytes,
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store, max-age=0",
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_name}",
        },
    )


@router.get("/messages/{message_id}/print", response_class=HTMLResponse)
def print_message_view(
    session_uuid: str,
    message_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Gera versão limpa e dedicada para impressão da mensagem (Seção 7.1),
    com CSS específico para papel, margens e paginação, contendo remetente,
    destinatários, assunto, data, corpo sanitizado e relação de anexos
    (sem incorporar automaticamente o conteúdo completo dos anexos).
    """
    pst_sess, folder, msg, atts, _ = _load_owned_message_and_attachments(
        db, session_uuid, message_id, auth
    )

    record_audit_event(
        db,
        event_type="PRINT_MESSAGE",
        event_result="SUCCESS",
        user_id=auth.user.id,
        username=auth.user.username,
        session_uuid=pst_sess.session_uuid,
        ip_address=auth.ip_address,
        details={"message_id": msg.id},
    )

    dt_str = (
        (msg.received_at or msg.sent_at).strftime("%d/%m/%Y %H:%M:%S")
        if (msg.received_at or msg.sent_at)
        else "Não informada"
    )
    sender_str = (
        f"{msg.sender_name} <{msg.sender_email}>"
        if (msg.sender_name and msg.sender_email)
        else (msg.sender_name or msg.sender_email or "Não informado")
    )

    cc_row = (
        f"<tr><th>CC:</th><td>{html.escape(msg.recipients_cc)}</td></tr>"
        if msg.recipients_cc
        else ""
    )
    bcc_row = (
        f"<tr><th>CCO:</th><td>{html.escape(msg.recipients_bcc)}</td></tr>"
        if msg.recipients_bcc
        else ""
    )

    att_items = ""
    if atts:
        lis = "".join(
            f"<li><strong>{html.escape(a.original_filename)}</strong> "
            f"({_format_size(a.size_bytes)} — {html.escape(a.mime_type)})</li>"
            for a in atts
        )
        att_items = f"""
        <div class="attachments-box">
            <div class="attachments-title">Relação de Anexos ({len(atts)}):</div>
            <ul>{lis}</ul>
        </div>
        """

    if msg.body_html_sanitized:
        from app.api.routes_reader import _resolve_inline_cid_images
        resolved_print_html = _resolve_inline_cid_images(msg.body_html_sanitized, session_uuid, atts)
        body_block = f'<div class="email-body-html">{resolved_print_html}</div>'
    else:
        escaped_plain = html.escape(msg.body_plain or "(Mensagem sem conteúdo textual)")
        body_block = f'<pre class="email-body-plain">{escaped_plain}</pre>'

    doc_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Imprimir E-mail - {html.escape(msg.subject or '(Sem assunto)')}</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 15mm 15mm 18mm 15mm;
        }}
        body {{
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
            color: #111827;
            background: #ffffff;
            margin: 0;
            padding: 24px;
            font-size: 10.5pt;
            line-height: 1.45;
        }}
        .no-print-bar {{
            background: #f3f4f6;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            padding: 10px 16px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .btn {{
            background: #0f6cbd;
            color: #fff;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
        }}
        .btn-sec {{
            background: #4b5563;
            color: #fff;
            border: none;
            padding: 8px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            margin-left: 8px;
        }}
        .print-header {{
            border-bottom: 2px solid #1f2937;
            padding-bottom: 10px;
            margin-bottom: 14px;
        }}
        .print-subject {{
            font-size: 15pt;
            font-weight: 700;
            margin: 0 0 8px 0;
            word-break: break-word;
        }}
        .meta-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 14px;
        }}
        .meta-table th {{
            text-align: left;
            width: 110px;
            color: #4b5563;
            font-weight: 600;
            padding: 3px 8px 3px 0;
            vertical-align: top;
        }}
        .meta-table td {{
            padding: 3px 0;
            word-break: break-word;
        }}
        .attachments-box {{
            border: 1px solid #d1d5db;
            background: #f9fafb;
            border-radius: 4px;
            padding: 10px 14px;
            margin-bottom: 16px;
            page-break-inside: avoid;
        }}
        .attachments-title {{
            font-weight: 600;
            margin-bottom: 6px;
            font-size: 10pt;
        }}
        .attachments-box ul {{
            margin: 0;
            padding-left: 18px;
            font-size: 9.5pt;
        }}
        .email-body-plain {{
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: inherit;
            font-size: 10.5pt;
            margin: 0;
        }}
        .email-body-html {{
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .email-body-html img {{
            max-width: 100%;
            height: auto;
        }}
        @media print {{
            body {{
                padding: 0;
            }}
            .no-print-bar {{
                display: none !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="no-print-bar">
        <div><strong>PST Viewer</strong> — Visualização de Impressão</div>
        <div>
            <button class="btn" onclick="window.print()">Imprimir agora</button>
            <button class="btn-sec" onclick="window.close()">Fechar</button>
        </div>
    </div>

    <div class="print-header">
        <h1 class="print-subject">{html.escape(msg.subject or '(Sem assunto)')}</h1>
        <table class="meta-table">
            <tr><th>De:</th><td>{html.escape(sender_str)}</td></tr>
            <tr><th>Para:</th><td>{html.escape(msg.recipients_to or '-')}</td></tr>
            {cc_row}
            {bcc_row}
            <tr><th>Data/Hora:</th><td>{html.escape(dt_str)}</td></tr>
            <tr><th>Pasta PST:</th><td>{html.escape(folder.full_path if folder else '')}</td></tr>
        </table>
    </div>

    {att_items}

    <div class="print-content">
        {body_block}
    </div>
</body>
</html>"""
    return HTMLResponse(content=doc_html)


@router.get("/attachments/{attachment_id}/print", response_class=HTMLResponse)
def print_attachment_view(
    session_uuid: str,
    attachment_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Operação separada para impressão de um anexo compatível (Seção 6 e Seção 7.1).
    """
    from app.api.routes_search_attachments import _get_verified_attachment

    pst_sess, att, _ = _get_verified_attachment(db, session_uuid, attachment_id, auth)

    record_audit_event(
        db,
        event_type="PRINT_ATTACHMENT",
        event_result="SUCCESS",
        user_id=auth.user.id,
        username=auth.user.username,
        session_uuid=pst_sess.session_uuid,
        ip_address=auth.ip_address,
        details={"attachment_id": att.id, "mime_type": att.mime_type},
    )

    if att.mime_type.startswith("image/"):
        body_html = f'<img src="/api/sessions/{session_uuid}/attachments/{att.id}/view" style="max-width:100%;height:auto;">'
    elif att.extracted_text:
        body_html = f'<pre style="white-space:pre-wrap;word-wrap:break-word;font-family:inherit;font-size:10.5pt;">{html.escape(att.extracted_text)}</pre>'
    else:
        body_html = (
            f"<p>Este formato ({html.escape(att.mime_type)}) não possui versão textual direta para impressão HTML. "
            f'Abra a <a href="/api/sessions/{session_uuid}/attachments/{att.id}/view">visualização nativa</a> ou baixe o arquivo.</p>'
        )

    doc_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Imprimir Anexo - {html.escape(att.original_filename)}</title>
    <style>
        @page {{ size: A4 portrait; margin: 15mm; }}
        body {{ font-family: "Segoe UI", Arial, sans-serif; padding: 24px; color: #111827; }}
        .no-print-bar {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 10px 16px; margin-bottom: 20px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; }}
        .btn {{ background: #0f6cbd; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: 600; }}
        .hdr {{ border-bottom: 2px solid #1f2937; padding-bottom: 8px; margin-bottom: 16px; }}
        @media print {{ body {{ padding: 0; }} .no-print-bar {{ display: none !important; }} }}
    </style>
</head>
<body>
    <div class="no-print-bar">
        <div><strong>PST Viewer</strong> — Impressão Separada de Anexo</div>
        <div><button class="btn" onclick="window.print()">Imprimir Anexo</button></div>
    </div>
    <div class="hdr">
        <h2 style="margin:0 0 6px 0;">Anexo: {html.escape(att.original_filename)}</h2>
        <div style="font-size:9.5pt;color:#4b5563;">Tamanho: {_format_size(att.size_bytes)} | Tipo: {html.escape(att.mime_type)} | SHA-256: {html.escape(att.sha256 or 'N/A')}</div>
    </div>
    <div>{body_html}</div>
</body>
</html>"""
    return HTMLResponse(content=doc_html)

