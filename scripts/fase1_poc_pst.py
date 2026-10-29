#!/usr/bin/env python3
"""
PST Viewer - Fase 1: Prova de Conceito (PoC) de Leitura de Arquivos PST
Valida cabeçalho binário (!BDN), tipo ANSI/Unicode, árvore de pastas,
extração em lotes de mensagens, cabeçalhos MAPI, anexos e geração de EML.
"""

from __future__ import annotations

import argparse
import email.policy
from email.message import EmailMessage
from email.utils import format_datetime
import hashlib
import json
import mimetypes
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PST_MAGIC = b"!BDN"


def get_rss_mb() -> float:
    """Retorna o pico de memória RSS do processo atual em MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Em Linux ru_maxrss é em KB
    return round(usage / 1024.0, 2)


def validate_pst_header(file_path: Path) -> Dict[str, Any]:
    """
    Valida assinatura binária do arquivo PST/OST sem confiar apenas na extensão.
    Estrutura do cabeçalho PFF:
      - Bytes 0..3: 0x21 0x42 0x44 0x4E ("!BDN")
      - Bytes 8..9: wMagicClient (SM = 0x53 0x4D para PST)
      - Bytes 10..11: wVer (14/15 = ANSI 97-2002; 21 = Unicode; 23 = Unicode Outlook 2003+; 36 = OST 2013+)
      - Byte 472 (ANSI) ou 513 (Unicode): bCryptMethod (0=None, 1=Permute/Compressible, 2=Cyclic/High)
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    size = file_path.stat().st_size
    if size < 564:
        raise ValueError("Arquivo menor que o cabeçalho mínimo de um PST válido (< 564 bytes).")

    with file_path.open("rb") as f:
        header = f.read(564)

    magic = header[0:4]
    if magic != PST_MAGIC:
        raise ValueError(f"Assinatura inválida: esperado '!BDN' (0x2142444E), encontrado {magic!r}")

    client_magic = header[8:10]
    w_ver = int.from_bytes(header[10:12], byteorder="little", signed=False)

    if w_ver in (14, 15):
        pst_type = "ANSI (32-bit, Outlook 97-2002)"
        crypt_byte = header[472]
    elif w_ver >= 21:
        pst_type = f"Unicode (64-bit, wVer={w_ver})"
        crypt_byte = header[513]
    else:
        pst_type = f"Desconhecido (wVer={w_ver})"
        crypt_byte = 0

    crypt_map = {
        0x00: "Nenhuma (0x00)",
        0x01: "Permutação / Compressível (0x01)",
        0x02: "Cíclica / Alta (0x02)",
    }

    return {
        "valid_signature": True,
        "file_size_bytes": size,
        "file_size_mb": round(size / (1024 * 1024), 2),
        "client_magic": client_magic.decode("ascii", errors="replace"),
        "w_ver": w_ver,
        "pst_format": pst_type,
        "encryption_method": crypt_map.get(crypt_byte, f"Outro/Criptografado (0x{crypt_byte:02x})"),
    }


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calcula o SHA-256 em streaming sem carregar o arquivo inteiro em RAM."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def safe_decode(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        for enc in ("utf-8", "cp1252", "latin-1", "utf-16-le"):
            try:
                return bytes(value).decode(enc)
            except UnicodeDecodeError:
                continue
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def build_sample_eml(msg_data: Dict[str, Any]) -> bytes:
    """Constrói um arquivo EML RFC 5322 válido a partir dos metadados e corpos extraídos."""
    eml = EmailMessage(policy=email.policy.SMTP)
    eml["Subject"] = msg_data.get("subject") or "(Sem assunto)"
    eml["From"] = msg_data.get("sender") or "desconhecido@local.invalid"
    if msg_data.get("to"):
        eml["To"] = msg_data["to"]
    if msg_data.get("cc"):
        eml["Cc"] = msg_data["cc"]
    if msg_data.get("delivery_time"):
        try:
            dt = datetime.fromisoformat(msg_data["delivery_time"])
            eml["Date"] = format_datetime(dt)
        except Exception:
            pass
    eml["X-PSTViewer-Reconstructed"] = "true"

    plain_body = msg_data.get("plain_body") or ""
    html_body = msg_data.get("html_body") or ""

    if plain_body and html_body:
        eml.set_content(plain_body)
        eml.add_alternative(html_body, subtype="html")
    elif html_body:
        eml.set_content("Mensagem originalmente em HTML.", subtype="plain")
        eml.add_alternative(html_body, subtype="html")
    else:
        eml.set_content(plain_body or "(Corpo vazio)")

    for att in msg_data.get("attachments_raw", []):
        ctype, _ = mimetypes.guess_type(att["filename"])
        if ctype:
            maintype, subtype = ctype.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        eml.add_attachment(
            att["content"],
            maintype=maintype,
            subtype=subtype,
            filename=att["filename"],
        )

    return eml.as_bytes()


def inspect_with_pypff(
    pst_path: Path,
    max_messages_sample: int = 20,
    export_sample_eml: Optional[Path] = None,
) -> Dict[str, Any]:
    """Realiza leitura hierárquica do PST usando pypff (libpff)."""
    import pypff  # type: ignore

    stats: Dict[str, Any] = {
        "engine": f"pypff ({pypff.get_version()})",
        "total_folders": 0,
        "total_messages": 0,
        "total_attachments": 0,
        "corrupted_items": 0,
        "folders": [],
        "sample_messages": [],
    }

    pff_file = pypff.file()
    pff_file.open(str(pst_path))

    try:
        root = pff_file.get_root_folder()
        if not root:
            return stats

        def walk_folder(folder: Any, parent_path: str = "") -> None:
            name = safe_decode(getattr(folder, "name", None)) or "Raiz"
            current_path = f"{parent_path}/{name}" if parent_path else f"/{name}"
            num_msgs = getattr(folder, "number_of_sub_messages", 0) or 0
            num_subs = getattr(folder, "number_of_sub_folders", 0) or 0

            stats["total_folders"] += 1
            stats["folders"].append(
                {
                    "path": current_path,
                    "name": name,
                    "messages_count": num_msgs,
                    "subfolders_count": num_subs,
                }
            )

            for i in range(num_msgs):
                try:
                    msg = folder.get_sub_message(i)
                    stats["total_messages"] += 1
                    num_att = getattr(msg, "number_of_attachments", 0) or 0
                    stats["total_attachments"] += num_att

                    if len(stats["sample_messages"]) < max_messages_sample:
                        subject = safe_decode(getattr(msg, "subject", None))
                        sender_name = safe_decode(getattr(msg, "sender_name", None))
                        headers = safe_decode(getattr(msg, "transport_headers", None))
                        plain_body = safe_decode(getattr(msg, "plain_text_body", None))
                        html_body = safe_decode(getattr(msg, "html_body", None))
                        delivery_time = getattr(msg, "delivery_time", None)
                        delivery_iso = (
                            delivery_time.replace(tzinfo=timezone.utc).isoformat()
                            if isinstance(delivery_time, datetime)
                            else None
                        )

                        att_meta: List[Dict[str, Any]] = []
                        att_raw: List[Dict[str, Any]] = []
                        for a_idx in range(num_att):
                            try:
                                att = msg.get_attachment(a_idx)
                                att_size = getattr(att, "size", 0) or 0
                                att_name = (
                                    safe_decode(getattr(att, "name", None))
                                    or f"anexo_{a_idx + 1}.bin"
                                )
                                att_meta.append({"name": att_name, "size": att_size})
                                if (
                                    export_sample_eml is not None
                                    and len(stats["sample_messages"]) == 0
                                    and att_size <= 5 * 1024 * 1024
                                ):
                                    att.seek_offset(0, os.SEEK_SET)
                                    raw_bytes = att.read_buffer(att_size)
                                    att_raw.append(
                                        {"filename": att_name, "content": raw_bytes}
                                    )
                            except Exception:
                                stats["corrupted_items"] += 1

                        sample_entry = {
                            "folder_path": current_path,
                            "subject": subject,
                            "sender": sender_name,
                            "delivery_time": delivery_iso,
                            "has_transport_headers": bool(headers),
                            "has_plain_body": bool(plain_body),
                            "has_html_body": bool(html_body),
                            "attachments_count": num_att,
                            "attachments": att_meta,
                        }
                        stats["sample_messages"].append(sample_entry)

                        if (
                            export_sample_eml is not None
                            and len(stats["sample_messages"]) == 1
                        ):
                            eml_bytes = build_sample_eml(
                                {
                                    "subject": subject,
                                    "sender": sender_name,
                                    "delivery_time": delivery_iso,
                                    "plain_body": plain_body,
                                    "html_body": html_body,
                                    "attachments_raw": att_raw,
                                }
                            )
                            export_sample_eml.write_bytes(eml_bytes)
                except Exception:
                    stats["corrupted_items"] += 1

            for j in range(num_subs):
                try:
                    sub = folder.get_sub_folder(j)
                    walk_folder(sub, current_path)
                except Exception:
                    stats["corrupted_items"] += 1

        walk_folder(root)
    finally:
        pff_file.close()

    return stats


def inspect_with_readpst_fallback(pst_path: Path) -> Dict[str, Any]:
    """Fallback usando readpst (pst-utils) em diretório temporário isolado."""
    readpst_bin = shutil.which("readpst")
    if not readpst_bin:
        raise RuntimeError(
            "Nem 'python3-pypff' nem 'readpst' (pst-utils) estão instalados no sistema."
        )

    with tempfile.TemporaryDirectory(prefix="pstviewer_poc_") as tmpdir:
        cmd = [readpst_bin, "-e", "-D", "-o", tmpdir, str(pst_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        root_tmp = Path(tmpdir)
        eml_files = list(root_tmp.rglob("*.eml"))
        folders = {str(p.parent.relative_to(root_tmp)) for p in eml_files}
        return {
            "engine": f"readpst ({readpst_bin})",
            "return_code": proc.returncode,
            "total_folders": len(folders),
            "total_messages": len(eml_files),
            "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
            "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PST Viewer - Fase 1: Prova Técnica de Leitura de PST"
    )
    parser.add_argument("pst_file", type=Path, help="Caminho para o arquivo .pst de teste")
    parser.add_argument(
        "--export-eml",
        type=Path,
        default=None,
        help="Caminho opcional para salvar a primeira mensagem extraída como .eml",
    )
    args = parser.parse_args()

    t0 = time.monotonic()
    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": str(args.pst_file.resolve()),
    }

    try:
        report["header_check"] = validate_pst_header(args.pst_file)
        report["sha256"] = compute_sha256(args.pst_file)

        try:
            report["extraction"] = inspect_with_pypff(
                args.pst_file, export_sample_eml=args.export_eml
            )
        except ImportError:
            report["extraction"] = inspect_with_readpst_fallback(args.pst_file)

        report["metrics"] = {
            "elapsed_seconds": round(time.monotonic() - t0, 3),
            "peak_rss_mb": get_rss_mb(),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        report["error"] = str(exc)
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

