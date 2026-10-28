"""Database-backed job queue. Claims are atomic (UPDATE ... WHERE status='queued'), so several workers are safe.

Handlers receive (db, job, ctx) and must check ctx.cancelled() inside long loops.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.logging import log_event
from app.db.session import session_scope
from app.models import Job

log = logging.getLogger("nexus.jobs")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
ACTIVE = ("queued", "running")


class JobContext:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._last_check = 0.0
        self._cancelled = False

    def cancelled(self) -> bool:
        now = time.monotonic()
        if now - self._last_check > 0.5:
            self._last_check = now
            with session_scope() as db:
                self._cancelled = bool(db.scalar(select(Job.cancel_requested).where(Job.id == self.job_id)))
        return self._cancelled

    def progress(self, current: int, total: int) -> None:
        with session_scope() as db:
            db.execute(update(Job).where(Job.id == self.job_id).values(progress_current=current, progress_total=total))


class JobFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


Handler = Callable[[Session, Job, JobContext], None]
Failer = Callable[[Session, Job, str, str], None]
HANDLERS: dict[str, tuple[Handler, Failer]] = {}


def register(kind: str, handler: Handler, on_fail: Failer) -> None:
    HANDLERS[kind] = (handler, on_fail)


def enqueue(db: Session, owner_id: str, kind: str, target_id: str) -> Job:
    running = db.scalar(select(func.count()).where(Job.owner_id == owner_id, Job.status.in_(ACTIVE))) or 0
    if running >= get_settings().max_parallel_jobs_per_user:
        raise ApiError(429, "too_many_jobs", f"You already have {running} active jobs. Wait until one finishes.")
    job = Job(owner_id=owner_id, kind=kind, target_id=target_id)
    db.add(job)
    db.flush()
    return job


def after_commit(job_id: str) -> None:
    """In inline mode (tests) run the job right away; otherwise the worker picks it up."""
    if get_settings().jobs_mode == "inline":
        run_job(job_id)


def claim(db: Session, job_id: str) -> bool:
    res = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "queued")
        .values(status="running", locked_by=WORKER_ID, started_at=datetime.now(UTC), attempts=Job.attempts + 1)
    )
    db.commit()
    return getattr(res, "rowcount", 0) == 1


def run_job(job_id: str) -> None:
    with session_scope() as db:
        if not claim(db, job_id):
            return
    status, code, message = "completed", None, None
    with session_scope() as db:
        job = db.get(Job, job_id)
        assert job is not None
        handler, on_fail = HANDLERS[job.kind]
        try:
            handler(db, job, JobContext(job_id))
            db.flush()
        except JobFailure as exc:
            db.rollback()
            status, code, message = ("cancelled" if exc.code == "cancelled" else "failed"), exc.code, exc.message
        except Exception as exc:
            db.rollback()
            log.exception("job crashed", extra={"extra_fields": {"job_id": job_id, "kind": job.kind}})
            status, code, message = "failed", "internal_error", f"Unexpected error ({type(exc).__name__})."
    with session_scope() as db:
        job = db.get(Job, job_id)
        assert job is not None
        if status != "completed":
            _, on_fail = HANDLERS[job.kind]
            on_fail(db, job, code or "failed", message or "")
        job.status, job.error_code, job.error_message = status, code, message
        job.finished_at = datetime.now(UTC)
    log_event(log, "job finished", job_id=job_id, status=status, code=code)


def recover_stale(db: Session) -> int:
    """Jobs stuck in 'running' longer than the timeout are failed, not retried, to avoid duplicate work."""
    limit = datetime.now(UTC) - timedelta(seconds=get_settings().job_timeout_seconds)
    stale = list(db.scalars(select(Job).where(Job.status == "running", Job.started_at < limit)))
    for job in stale:
        _, on_fail = HANDLERS.get(job.kind, (None, None))
        if on_fail:
            on_fail(db, job, "timeout", "The job exceeded the time limit or the worker stopped.")
        job.status, job.error_code, job.error_message = "failed", "timeout", "Job exceeded the time limit."
        job.finished_at = datetime.now(UTC)
    return len(stale)


def work_once(extra_tick: Callable[[], None] | None = None) -> int:
    with session_scope() as db:
        ids = list(db.scalars(select(Job.id).where(Job.status == "queued").order_by(Job.created_at).limit(5)))
        recover_stale(db)
    for jid in ids:
        run_job(jid)
    if extra_tick:
        extra_tick()
    return len(ids)


class WorkerThread(threading.Thread):
    def __init__(self, tick: Callable[[], None] | None = None) -> None:
        super().__init__(name="nexus-worker", daemon=True)
        self._stop_event = threading.Event()
        self._tick = tick

    def run(self) -> None:
        interval = get_settings().worker_poll_seconds
        while not self._stop_event.is_set():
            try:
                work_once(self._tick)
            except Exception:
                log.exception("worker loop error")
            self._stop_event.wait(interval)

    def stop(self) -> None:
        self._stop_event.set()


def job_payload(job: Job | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "cancel_requested": job.cancel_requested,
    }


def latest_job(db: Session, target_id: str) -> Job | None:
    return db.scalar(select(Job).where(Job.target_id == target_id).order_by(Job.created_at.desc()).limit(1))
