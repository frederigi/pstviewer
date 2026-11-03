#!/usr/bin/env python3
"""
Guardião Independente de Limpeza de Sessões Temporárias (Seção 9.1).
Verifica e expurga sessões expiradas/abandonadas e diretórios órfãos,
mesmo quando o navegador é fechado inesperadamente ou o computador do usuário é desligado.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time

from app.database.session import SessionLocal
from app.services.cleanup_service import sweep_expired_and_orphan_sessions

_RUNNING = True


def _handle_signal(signum: int, _frame: object) -> None:
    global _RUNNING
    _RUNNING = False


def run_once() -> dict:
    with SessionLocal() as db:
        return sweep_expired_and_orphan_sessions(db)


def main() -> int:
    parser = argparse.ArgumentParser(description="PST Viewer - Guardião de Limpeza Temporária")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa uma única varredura e encerra (ideal para systemd timer ou testes).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Intervalo em segundos entre varreduras no modo contínuo (padrão: 60s).",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if args.once:
        summary = run_once()
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    while _RUNNING:
        try:
            summary = run_once()
            if (
                summary["purged_sessions"]
                or summary["failed_sessions"]
                or summary["orphan_dirs_removed"]
            ):
                print(json.dumps(summary, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(f"[ERRO CLEANER] {exc}", file=sys.stderr, flush=True)

        for _ in range(args.interval):
            if not _RUNNING:
                break
            time.sleep(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())

