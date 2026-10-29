"""
Extração Segura de Metadados e Conteúdo Textual de Anexos (Seção 6).
Suporta PDF, TXT, CSV, HTML, RTF, DOCX, XLSX, PPTX e DOC legado,
com proteção contra Zip Bombs, detecção de senha/criptografia,
limites de tamanho/tempo/memória e OCR opcional com Tesseract.
"""

from __future__ import annotations

from pathlib import Path
import mimetypes
import re
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple
import zipfile

from charset_normalizer import from_bytes
from docx import Document as DocxDocument
from openpyxl import load_workbook
from pptx import Presentation
from striprtf.striprtf import rtf_to_text

from app.services.html_sanitizer import html_to_plain_text

SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._\-\sÀ-ÿ]")
MAX_EXTRACTED_TEXT_CHARS = 250_000
MAX_ZIP_ENTRIES = 2500
MAX_ZIP_UNCOMPRESSED_BYTES = 120 * 1024 * 1024  # 120 MB
SUBPROCESS_TIMEOUT_SEC = 15


def sanitize_attachment_filename(raw_name: Optional[str], default_index: int = 1) -> str:
    if not raw_name:
        return f"anexo_{default_index}.bin"
    base = Path(raw_name.replace("\\", "/")).name.strip()
    cleaned = SAFE_FILENAME_RE.sub("_", base).strip("._ ")
    if not cleaned:
        return f"anexo_{default_index}.bin"
    return cleaned[:200]


def detect_mime_and_signature(file_path: Path, filename: str) -> str:
    """Detecta o MIME real combinando assinatura mágica dos primeiros bytes e extensão."""
    try:
        with file_path.open("rb") as f:
            head = f.read(512)
    except Exception:
        head = b""

    ext = Path(filename).suffix.lower()

    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"{\\rtf"):
        return "application/rtf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"PK\x03\x04"):
        if ext == ".docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if ext == ".xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if ext == ".pptx":
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return "application/zip"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        # Container OLE2: pode ser DOC/XLS legado ou DOCX/XLSX criptografado com senha!
        if b"E\x00n\x00c\x00r\x00y\x00p\x00t\x00e\x00d\x00P\x00a\x00c\x00k\x00a\x00g\x00e" in head or (
            b"EncryptedPackage" in file_path.read_bytes()[:65536]
        ):
            return "application/x-office-encrypted"
        if ext == ".doc":
            return "application/msword"
        if ext == ".xls":
            return "application/vnd.ms-excel"
        return "application/x-ole-storage"

    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _check_zip_safety(file_path: Path) -> Tuple[bool, str]:
    """Verifica se um arquivo ZIP/OOXML é seguro (sem Zip Bomb e sem criptografia)."""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                return False, f"Excesso de entradas internas no pacote ({len(infos)} > {MAX_ZIP_ENTRIES})"
            total_uncompressed = 0
            for info in infos:
                if info.flag_bits & 0x1:
                    return False, "ENCRYPTED_OR_PASSWORD"
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
                    return False, "Limite de expansão descompactada excedido (proteção Zip Bomb)"
        return True, "OK"
    except zipfile.BadZipFile:
        return False, "CORRUPTED"
    except Exception as exc:
        return False, str(exc)


def _extract_pdf(file_path: Path, enable_ocr: bool = False) -> Tuple[str, str, Dict[str, Any]]:
    meta: Dict[str, Any] = {"format": "PDF"}
    pdfinfo_bin = shutil.which("pdfinfo")
    if pdfinfo_bin:
        proc_info = subprocess.run(
            [pdfinfo_bin, str(file_path)],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SEC,
        )
        if proc_info.returncode != 0 and "Incorrect password" in (proc_info.stderr or ""):
            return "ENCRYPTED_OR_PASSWORD", "", {"format": "PDF", "encrypted": True}
        for line in (proc_info.stdout or "").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k_clean = k.strip().lower().replace(" ", "_")
                if k_clean in ("pages", "encrypted", "page_size", "pdf_version", "title", "author"):
                    meta[k_clean] = v.strip()
        if str(meta.get("encrypted", "")).lower().startswith("yes"):
            return "ENCRYPTED_OR_PASSWORD", "", meta

    pdftotext_bin = shutil.which("pdftotext")
    if not pdftotext_bin:
        return "EXTRACTED", "", meta

    proc_txt = subprocess.run(
        [pdftotext_bin, "-l", "150", "-q", str(file_path), "-"],
        capture_output=True,
        text=True,
         errors="replace",
        timeout=SUBPROCESS_TIMEOUT_SEC,
    )
    if proc_txt.returncode != 0:
        return "CORRUPTED", "", meta

    text = (proc_txt.stdout or "").strip()
    if not text and enable_ocr:
        tesseract_bin = shutil.which("tesseract")
        if tesseract_bin:
            meta["ocr_attempted"] = True
    if text:
        return "TEXT_INDEXED", text[:MAX_EXTRACTED_TEXT_CHARS], meta
    return "EXTRACTED", "", meta


def _extract_docx(file_path: Path) -> Tuple[str, str, Dict[str, Any]]:
    safe, reason = _check_zip_safety(file_path)
    if not safe:
        status = "ENCRYPTED_OR_PASSWORD" if reason == "ENCRYPTED_OR_PASSWORD" else "CORRUPTED"
        return status, "", {"format": "DOCX", "warning": reason}

    doc = DocxDocument(str(file_path))
    parts = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables[:50]:
        for row in table.rows[:200]:
            row_txt = " | ".join(c.text.strip() for c in row.cells if c.text and c.text.strip())
            if row_txt:
                parts.append(row_txt)
    full_txt = "\n".join(parts)[:MAX_EXTRACTED_TEXT_CHARS]
    return (
        ("TEXT_INDEXED" if full_txt else "EXTRACTED"),
        full_txt,
        {"format": "DOCX", "paragraphs": len(doc.paragraphs), "tables": len(doc.tables)},
    )


def _extract_xlsx(file_path: Path) -> Tuple[str, str, Dict[str, Any]]:
    safe, reason = _check_zip_safety(file_path)
    if not safe:
        status = "ENCRYPTED_OR_PASSWORD" if reason == "ENCRYPTED_OR_PASSWORD" else "CORRUPTED"
        return status, "", {"format": "XLSX", "warning": reason}

    wb = load_workbook(filename=str(file_path), read_only=True, data_only=True)
    sheet_names = wb.sheetnames[:30]
    lines = []
    try:
        for sname in sheet_names:
            ws = wb[sname]
            lines.append(f"[Planilha: {sname}]")
            row_count = 0
            for row in ws.iter_rows(values_only=True):
                row_count += 1
                if row_count > 2000:
                    break
                vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if vals:
                    lines.append(" | ".join(vals))
    finally:
        wb.close()

    full_txt = "\n".join(lines)[:MAX_EXTRACTED_TEXT_CHARS]
    return (
        ("TEXT_INDEXED" if full_txt else "EXTRACTED"),
        full_txt,
        {"format": "XLSX", "sheets": sheet_names},
    )


def _extract_pptx(file_path: Path) -> Tuple[str, str, Dict[str, Any]]:
    safe, reason = _check_zip_safety(file_path)
    if not safe:
        status = "ENCRYPTED_OR_PASSWORD" if reason == "ENCRYPTED_OR_PASSWORD" else "CORRUPTED"
        return status, "", {"format": "PPTX", "warning": reason}

    prs = Presentation(str(file_path))
    lines = []
    for idx, slide in enumerate(prs.slides, start=1):
        if idx > 150:
            break
        slide_texts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                txt = shape.text_frame.text.strip()
                if txt:
                    slide_texts.append(txt)
        if slide_texts:
            lines.append(f"[Slide {idx}] " + " ".join(slide_texts))

    full_txt = "\n".join(lines)[:MAX_EXTRACTED_TEXT_CHARS]
    return (
        ("TEXT_INDEXED" if full_txt else "EXTRACTED"),
        full_txt,
        {"format": "PPTX", "slides": len(prs.slides)},
    )


def _decode_bytes_safely(raw_bytes: bytes) -> str:
    if not raw_bytes:
        return ""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    best = from_bytes(raw_bytes).best()
    if best is not None:
        return str(best)
    return raw_bytes.decode("utf-8", errors="replace")


def extract_attachment_text_and_metadata(
    file_path: Path,
    filename: str,
    mime_type: str,
    max_extract_mb: int = 50,
    enable_ocr: bool = False,
) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """
    Analisa o anexo salvo no disco e retorna:
      (extraction_status, extracted_text, metadata_json)
    """
    size_bytes = file_path.stat().st_size
    if size_bytes > max_extract_mb * 1024 * 1024:
        return (
            "SIZE_LIMIT_EXCEEDED",
            None,
            {"size_bytes": size_bytes, "limit_mb": max_extract_mb},
        )

    if mime_type == "application/x-office-encrypted":
        return (
            "ENCRYPTED_OR_PASSWORD",
            None,
            {"encrypted": True, "note": "Documento Office protegido por senha"},
        )

    ext = Path(filename).suffix.lower()

    try:
        if mime_type == "application/pdf" or ext == ".pdf":
            status, txt, meta = _extract_pdf(file_path, enable_ocr=enable_ocr)
            return status, (txt or None), meta

        if ext == ".docx" or mime_type.endswith("wordprocessingml.document"):
            status, txt, meta = _extract_docx(file_path)
            return status, (txt or None), meta

        if ext == ".xlsx" or mime_type.endswith("spreadsheetml.sheet"):
            status, txt, meta = _extract_xlsx(file_path)
            return status, (txt or None), meta

        if ext == ".pptx" or mime_type.endswith("presentationml.presentation"):
            status, txt, meta = _extract_pptx(file_path)
            return status, (txt or None), meta

        if ext in (".txt", ".csv", ".log", ".md") or mime_type.startswith("text/plain") or mime_type == "text/csv":
            raw = file_path.read_bytes()
            txt = _decode_bytes_safely(raw)[:MAX_EXTRACTED_TEXT_CHARS].strip()
            return ("TEXT_INDEXED" if txt else "EXTRACTED"), (txt or None), {"format": ext.upper().lstrip(".") or "TXT"}

        if ext in (".html", ".htm") or mime_type == "text/html":
            raw = file_path.read_bytes()
            html_str = _decode_bytes_safely(raw)
            txt = html_to_plain_text(html_str)[:MAX_EXTRACTED_TEXT_CHARS]
            return ("TEXT_INDEXED" if txt else "EXTRACTED"), (txt or None), {"format": "HTML"}

        if ext == ".rtf" or mime_type in ("application/rtf", "text/rtf"):
            raw = file_path.read_bytes()
            rtf_str = _decode_bytes_safely(raw)
            txt = rtf_to_text(rtf_str)[:MAX_EXTRACTED_TEXT_CHARS].strip()
            return ("TEXT_INDEXED" if txt else "EXTRACTED"), (txt or None), {"format": "RTF"}

        if ext == ".doc" or mime_type == "application/msword":
            antiword_bin = shutil.which("antiword") or shutil.which("catdoc")
            if antiword_bin:
                proc = subprocess.run(
                    [antiword_bin, str(file_path)],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=SUBPROCESS_TIMEOUT_SEC,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return (
                        "TEXT_INDEXED",
                        proc.stdout.strip()[:MAX_EXTRACTED_TEXT_CHARS],
                        {"format": "DOC"},
                    )
            return "EXTRACTED", None, {"format": "DOC"}

        if ext == ".zip" or mime_type == "application/zip":
            safe, reason = _check_zip_safety(file_path)
            if not safe:
                status = "ENCRYPTED_OR_PASSWORD" if reason == "ENCRYPTED_OR_PASSWORD" else "CORRUPTED"
                return status, None, {"format": "ZIP", "warning": reason}
            with zipfile.ZipFile(file_path, "r") as zf:
                names = [n for n in zf.namelist()[:200]]
            return "TEXT_INDEXED", "\n".join(names), {"format": "ZIP", "entries_count": len(names)}

        if mime_type.startswith("image/"):
            if enable_ocr and shutil.which("tesseract"):
                proc = subprocess.run(
                    ["tesseract", str(file_path), "stdout", "-l", "por+eng"],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=SUBPROCESS_TIMEOUT_SEC,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return (
                        "TEXT_INDEXED",
                        proc.stdout.strip()[:MAX_EXTRACTED_TEXT_CHARS],
                        {"format": "IMAGE", "ocr": True},
                    )
            return "EXTRACTED", None, {"format": "IMAGE"}

        return "UNSUPPORTED_FORMAT", None, {"mime_type": mime_type}

    except subprocess.TimeoutExpired:
        return "CORRUPTED", None, {"error": "Tempo limite de extração do anexo excedido"}
    except Exception as exc:
        return "CORRUPTED", None, {"error": str(exc)[:200]}

