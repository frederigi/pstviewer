#!/usr/bin/env python3
"""
Worker de Processamento PST em Segundo Plano (Fase 3 - Seções 5, 11 e 13).
Consome jobs `EXTRACT_PST` da fila persistente no MySQL (`background_jobs`),
inclui retomada automática após reinicialização do servidor e respeita limites de recursos.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sys
import time
from typing import Optional

from sqlalchemy import delete, or_, select

from app.database.models import (
    BackgroundJob,
    PstAttachment,
    PstFolder,
    PstMessage,
    PstSession,
)
from app.database.session import SessionLocal
from app.services.pst_extractor import process_pst_extraction_job
from app.services.session_manager import resolve_session_dir, utc_now

_RUNNING = True


def _handle_signal(signum: int, _frame: object) -> None:
    global _RUNNING
    _RUNNING = False


def _pid_is_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def recover_interrupted_jobs_on_startup() -> int:
    """
    Recupera tarefas de extração PST que estavam em estado RUNNING antes de uma
    reinicialização do sistema ou queda abrupta do worker (Seção 17).
    Limpa artefatos parciais da tentativa anterior para reprocessar sem duplicatas.
    """
    recovered = 0
    now = utc_now()
    with SessionLocal() as db:
        stale_jobs = list(
            db.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.job_type == "EXTRACT_PST",
                    BackgroundJob.status == "RUNNING",
                )
            ).all()
        )
        for job in stale_jobs:
            if _pid_is_alive(job.worker_pid) and job.worker_pid != os.getpid():
                continue

            sess = db.get(PstSession, job.pst_session_id)
            if (
                not sess
                or sess.status in ("CLOSING", "CLEANING", "PURGED", "CANCELLED")
                or sess.hard_expires_at <= now
                or job.attempts >= max(job.max_attempts, 6)
            ):
                job.status = "FAILED"
                job.finished_at = now
                job.last_error = "Interrompido e expirado ou limite de tentativas atingido."
                if sess and sess.status not in ("PURGED", "CLOSING"):
                    sess.status = "FAILED"
                    sess.diagnostic_summary = json.dumps(
                        {
                            "engine": "pypff",
                            "warnings": [
                                "O processamento foi interrompido repetidamente (reinicialização do worker ou limite de tentativas)."
                            ],
                        },
                        ensure_ascii=False,
                    )
                db.commit()
                continue

            # Remove extrações parciais no banco e anexos parciais no disco preservando original.pst
            db.execute(delete(PstAttachment).where(PstAttachment.pst_session_id == sess.id))
            db.execute(delete(PstMessage).where(PstMessage.pst_session_id == sess.id))
            db.execute(delete(PstFolder).where(PstFolder.pst_session_id == sess.id))

            session_dir = resolve_session_dir(sess.session_uuid)
            att_dir = session_dir / "attachments"
            if att_dir.exists():
                shutil.rmtree(att_dir, ignore_errors=True)
            att_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

            from datetime import timedelta

            sess.processed_folders = 0
            sess.processed_messages = 0
            sess.processed_attachments = 0
            sess.total_attachments = 0
            sess.corrupted_items = 0
            sess.disk_usage_bytes = sess.file_size_bytes
            sess.last_heartbeat_at = now
            if sess.idle_expires_at <= now:
                sess.idle_expires_at = now + timedelta(minutes=30)
            sess.status = "QUEUED"
            sess.current_stage = "Retomando extração após reinicialização do serviço"

            job.status = "PENDING"
            job.worker_pid = None
            db.commit()
            recovered += 1

    return recovered


def process_next_pending_job() -> Optional[dict]:
    """Busca o próximo job EXTRACT_PST pendente na fila e o executa."""
    now = utc_now()
    with SessionLocal() as db:
        stmt = (
            select(BackgroundJob)
            .where(
                BackgroundJob.job_type == "EXTRACT_PST",
                BackgroundJob.status == "PENDING",
                BackgroundJob.cancel_requested.is_(False),
                or_(
                    BackgroundJob.next_retry_at.is_(None),
                    BackgroundJob.next_retry_at <= now,
                ),
            )
            .order_by(BackgroundJob.priority.asc(), BackgroundJob.created_at.asc())
            .limit(1)
        )
        job = db.scalar(stmt)
        if not job:
            return None
        job_id = job.id

    with SessionLocal() as db:
        return process_pst_extraction_job(db, job_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="PST Viewer - Worker de Extração PST")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Processa um único job pendente da fila e encerra.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Intervalo em segundos quando a fila está vazia (padrão: 2s).",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    recovered = recover_interrupted_jobs_on_startup()
    if recovered:
        print(f"[WORKER] {recovered} job(s) interrompido(s) recuperado(s) para a fila.", flush=True)

    if args.once:
        res = process_next_pending_job()
        print(json.dumps(res or {"status": "NO_PENDING_JOBS"}, ensure_ascii=False))
        return 0

    while _RUNNING:
        try:
            res = process_next_pending_job()
            if res is not None:
                print(json.dumps(res, ensure_ascii=False), flush=True)
                continue
        except Exception as exc:
            print(f"[ERRO WORKER PST] {exc}", file=sys.stderr, flush=True)

        time.sleep(args.poll_interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())

