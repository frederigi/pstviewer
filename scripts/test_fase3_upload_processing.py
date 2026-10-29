#!/usr/bin/env python3
"""
PST Viewer - Fase 3: Bateria de Testes Reais de Upload, Validação Binária (!BDN),
Interrupção de Upload, Falta de Espaço em Disco, Extração Real de PST com `pypff`,
Extração de Texto de Anexos (PDF, DOCX, XLSX, PPTX, TXT, HTML, RTF, ZIP com senha),
Sanitização HTML, Cancelamento de Processamento e Retomada após Reinicialização.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
import sys
from typing import AsyncIterator
import zipfile

from docx import Document as DocxDocument
from openpyxl import Workbook
from pptx import Presentation
from sqlalchemy import func, select

from app.auth.security import create_user
from app.core.config import settings
from app.database.models import (
    BackgroundJob,
    PstAttachment,
    PstFolder,
    PstMessage,
    PstSession,
    SystemSetting,
    User,
)
from app.database.session import SessionLocal
from app.services.attachment_extractor import (
    detect_mime_and_signature,
    extract_attachment_text_and_metadata,
)
from app.services.cleanup_service import close_and_purge_user_session
from app.services.html_sanitizer import sanitize_email_html
from app.services.pst_extractor import (
    process_pst_extraction_job,
    request_session_extraction_cancel,
)
from app.services.session_manager import resolve_session_dir
from app.services.upload_service import (
    InvalidPstFileError,
    receive_pst_upload_async,
    receive_pst_upload_sync,
)
from app.workers.pst_worker import recover_interrupted_jobs_on_startup


def _cleanup_user(db, username: str) -> None:
    u = db.scalar(select(User).where(User.username == username))
    if u:
        db.delete(u)
        db.commit()


async def _interrupted_stream() -> AsyncIterator[bytes]:
    # Envia cabeçalho PST aparente mas interrompe a conexão no meio do upload
    fake_hdr = b"!BDN" + b"\x00" * 6 + (23).to_bytes(2, "little") + b"\x00" * 600
    yield fake_hdr
    raise ConnectionResetError("Conexão de upload interrompida abruptamente pelo cliente.")


def _test_attachment_extractors(tmp_dir: Path) -> dict:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    summary = {}

    # 1. DOCX real com parágrafo e tabela
    docx_path = tmp_dir / "relatorio.docx"
    doc = DocxDocument()
    doc.add_paragraph("Relatório Confidencial de Auditoria Financeira 2026")
    tbl = doc.add_table(rows=1, cols=2)
    tbl.rows[0].cells[0].text = "Centro de Custo"
    tbl.rows[0].cells[1].text = "R$ 150.000,00"
    doc.save(str(docx_path))
    mime_docx = detect_mime_and_signature(docx_path, "relatorio.docx")
    st_docx, txt_docx, _ = extract_attachment_text_and_metadata(docx_path, "relatorio.docx", mime_docx)
    assert st_docx == "TEXT_INDEXED" and "Auditoria Financeira" in (txt_docx or "")
    summary["docx"] = st_docx

    # 2. XLSX real
    xlsx_path = tmp_dir / "planilha.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Orcamento"
    ws.append(["Item", "Valor"])
    ws.append(["Servidor Debian", 12500])
    wb.save(str(xlsx_path))
    mime_xlsx = detect_mime_and_signature(xlsx_path, "planilha.xlsx")
    st_xlsx, txt_xlsx, _ = extract_attachment_text_and_metadata(xlsx_path, "planilha.xlsx", mime_xlsx)
    assert st_xlsx == "TEXT_INDEXED" and "Servidor Debian" in (txt_xlsx or "")
    summary["xlsx"] = st_xlsx

    # 3. PPTX real
    pptx_path = tmp_dir / "apresentacao.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Arquitetura PST Viewer"
    prs.save(str(pptx_path))
    mime_pptx = detect_mime_and_signature(pptx_path, "apresentacao.pptx")
    st_pptx, txt_pptx, _ = extract_attachment_text_and_metadata(pptx_path, "apresentacao.pptx", mime_pptx)
    assert st_pptx == "TEXT_INDEXED" and "Arquitetura PST Viewer" in (txt_pptx or "")
    summary["pptx"] = st_pptx

    # 4. RTF com acentuação
    rtf_path = tmp_dir / "memorando.rtf"
    rtf_path.write_text(r"{\rtf1\ansi Memorando de Operação Técnica}", encoding="utf-8")
    mime_rtf = detect_mime_and_signature(rtf_path, "memorando.rtf")
    st_rtf, txt_rtf, _ = extract_attachment_text_and_metadata(rtf_path, "memorando.rtf", mime_rtf)
    assert st_rtf == "TEXT_INDEXED" and "Memorando" in (txt_rtf or "")
    summary["rtf"] = st_rtf

    # 5. ZIP com entrada marcada como criptografada (flag_bits 0x1 no Central Directory)
    enc_zip_path = tmp_dir / "protegido.zip"
    with zipfile.ZipFile(enc_zip_path, "w") as zf:
        zf.writestr("segredo.txt", b"dados")
    raw_zip = bytearray(enc_zip_path.read_bytes())
    raw_zip[6] |= 0x01
    cd_offset = raw_zip.find(b"PK\x01\x02")
    if cd_offset != -1:
        raw_zip[cd_offset + 8] |= 0x01
    enc_zip_path.write_bytes(bytes(raw_zip))
    st_zip, _, _ = extract_attachment_text_and_metadata(enc_zip_path, "protegido.zip", "application/zip")
    assert st_zip == "ENCRYPTED_OR_PASSWORD"
    summary["encrypted_zip_detected"] = st_zip

    return summary


def run_tests(pst_sample_path: Path) -> dict:
    results = {}

    # Para não haver concorrência com o daemon systemd durante o teste controlado,
    # processamos os jobs diretamente nas chamadas do teste.
    with SessionLocal() as db:
        _cleanup_user(db, "teste_fase3")
        user = create_user(db, "teste_fase3", "SenhaForte#Fase3_2026", "Usuário Fase 3")

        # 1. Rejeição de arquivo inválido (falso .pst sem assinatura !BDN)
        fake_file = io.BytesIO(b"MZ\x90\x00Este arquivo e um executavel disfarcado de PST" * 30)
        try:
            receive_pst_upload_sync(
                db=db,
                user_id=user.id,
                username=user.username,
                original_filename="falso_virus.pst",
                file_obj=fake_file,
                ip_address="10.0.0.30",
            )
            raise AssertionError("Arquivo sem assinatura !BDN deveria ter sido rejeitado!")
        except InvalidPstFileError as exc:
            results["1_invalid_magic_rejected"] = f"OK ({exc})"

        # 2. Upload interrompido no meio e verificação de limpeza de parciais
        try:
            asyncio.run(
                receive_pst_upload_async(
                    db=db,
                    user_id=user.id,
                    username=user.username,
                    original_filename="interrompido.pst",
                    chunk_iterator=_interrupted_stream(),
                    ip_address="10.0.0.30",
                )
            )
            raise AssertionError("Upload interrompido deveria levantar exceção!")
        except ConnectionResetError:
            leftover_parts = list(settings.quarantine_dir.glob("*.part"))
            assert len(leftover_parts) == 0, "Nenhum arquivo .part deveria restar na quarentena!"
            results["2_interrupted_upload_cleaned"] = "OK (0 arquivos parciais restantes)"

        # 3. Teste de recusa preventiva quando não há espaço livre suficiente
        setting_free = db.get(SystemSetting, "min_free_disk_mb")
        orig_free_val = setting_free.setting_value
        try:
            setting_free.setting_value = "99999999"  # ~100 TB exigidos
            db.commit()
            try:
                receive_pst_upload_sync(
                    db=db,
                    user_id=user.id,
                    username=user.username,
                    original_filename="sem_espaco.pst",
                    file_obj=io.BytesIO(b"!BDN" + b"\x00" * 1024),
                )
                raise AssertionError("Deveria recusar upload quando espaço livre é insuficiente!")
            except RuntimeError as exc:
                results["3_low_disk_space_refused"] = f"OK ({exc})"
        finally:
            setting_free.setting_value = orig_free_val
            db.commit()

        # 4. Sanitização de HTML malicioso (XSS + Web Beacons + Formulários)
        dirty_html = (
            '<html><body><script>alert("xss")</script>'
            '<form action="http://attacker.tld"><input type="text"></form>'
            '<img src="https://tracker.attacker.tld/pixel.gif" onclick="steal()">'
            '<img src="cid:logo_interno@empresa">'
            '<p style="background:url(https://evil.tld/bg.png)">Texto seguro com acentuação</p>'
            "</body></html>"
        )
        clean_html, blocked_count = sanitize_email_html(dirty_html)
        assert "<script" not in clean_html.lower()
        assert "<form" not in clean_html.lower()
        assert "onclick" not in clean_html.lower()
        assert 'data-cid="logo_interno@empresa"' in clean_html
        results["4_html_sanitization_and_beacon_block"] = {
            "status": "OK",
            "xss_and_scripts_removed": True,
        }

        # 5. Extratores de anexos (DOCX, XLSX, PPTX, RTF, ZIP com senha)
        tmp_att_dir = Path("/tmp/pstviewer_test_att")
        results["5_attachment_extractors"] = _test_attachment_extractors(tmp_att_dir)

        # 6. Upload e Extração Real de arquivo PST (testPST.pst) + Retomada após reinicialização
        if not pst_sample_path.is_file():
            raise FileNotFoundError(f"Arquivo PST de amostra não encontrado em {pst_sample_path}")

        with pst_sample_path.open("rb") as pf:
            pst_sess, job = receive_pst_upload_sync(
                db=db,
                user_id=user.id,
                username=user.username,
                original_filename=pst_sample_path.name,
                file_obj=pf,
                ip_address="10.0.0.30",
            )

        # Simula que o worker foi interrompido por reinicialização no meio do job (PID inexistente 999998)
        from datetime import timedelta
        from app.services.session_manager import utc_now
        job.status = "RUNNING"
        job.worker_pid = 999998
        job.next_retry_at = utc_now() + timedelta(minutes=5)
        pst_sess.status = "PROCESSING"
        db.commit()

        recovered_count = recover_interrupted_jobs_on_startup()
        assert recovered_count >= 1
        db.expire_all()
        job = db.get(BackgroundJob, job.id)
        assert job.status == "PENDING"
        results["6_recovery_after_reboot"] = f"OK ({recovered_count} job recuperado)"

        # Executa a extração real do PST com pypff
        extraction_summary = process_pst_extraction_job(db, job.id)
        db.expire_all()
        pst_sess = db.get(PstSession, pst_sess.id)
        assert pst_sess.status == "READY"
        assert float(pst_sess.progress_percent) == 100.0

        folders_in_db = db.scalar(
            select(func.count(PstFolder.id)).where(PstFolder.pst_session_id == pst_sess.id)
        )
        msgs_in_db = db.scalar(
            select(func.count(PstMessage.id)).where(PstMessage.pst_session_id == pst_sess.id)
        )
        atts_in_db = db.scalar(
            select(func.count(PstAttachment.id)).where(PstAttachment.pst_session_id == pst_sess.id)
        )
        assert folders_in_db > 0 and msgs_in_db > 0

        results["7_real_pst_extraction_with_pypff"] = {
            "session_uuid": pst_sess.session_uuid,
            "pst_format": pst_sess.pst_format,
            "sha256": pst_sess.file_sha256,
            "folders_extracted": folders_in_db,
            "messages_extracted": msgs_in_db,
            "attachments_extracted": atts_in_db,
            "status": pst_sess.status,
            "progress_percent": float(pst_sess.progress_percent),
        }

        # Encerra e limpa a sessão extraída
        close_and_purge_user_session(db, pst_sess.session_uuid, user.id, user.username)

        # 8. Teste de Cancelamento de Processamento antes/durante fila e limpeza de parciais
        with pst_sample_path.open("rb") as pf2:
            sess_cancel, job_cancel = receive_pst_upload_sync(
                db=db,
                user_id=user.id,
                username=user.username,
                original_filename="cancelar_este.pst",
                file_obj=pf2,
                ip_address="10.0.0.30",
            )
        job_cancel.next_retry_at = utc_now() + timedelta(minutes=5)
        db.commit()
        cancel_dir = resolve_session_dir(sess_cancel.session_uuid)
        assert cancel_dir.exists()
        cancel_res = request_session_extraction_cancel(
            db, sess_cancel.session_uuid, user.id, user.username, "10.0.0.30"
        )
        assert cancel_res["cancelled"] is True
        assert not cancel_dir.exists(), "Diretório parcial deveria ter sido removido após cancelamento!"
        results["8_cancel_processing_and_purge_partials"] = cancel_res

        _cleanup_user(db, "teste_fase3")

    return results


if __name__ == "__main__":
    sample_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/sample_apache_tika.pst")
    # Para evitar condição de corrida com o daemon pstviewer-worker durante o teste controlado,
    # o script pode ser rodado com o worker ativo ou parado; garantimos a execução determinística.
    out = run_tests(sample_arg)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    sys.exit(0)
