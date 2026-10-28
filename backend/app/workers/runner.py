"""Standalone job worker: `python -m app.workers.runner`. Run one or more next to the API (JOBS_MODE=external)."""

from __future__ import annotations

import logging
import signal
import time

import app.services.ai.agent  # noqa: F401  (registers job handlers)
import app.services.runs  # noqa: F401  (registers job handlers)
from app.core.config import get_settings
from app.core.logging import log_event, setup_logging
from app.services.jobs import work_once
from app.services.paper import auto_tick

log = logging.getLogger("nexus.worker")


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    running = True

    def _stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log_event(log, "worker started", poll=settings.worker_poll_seconds)
    while running:
        try:
            if work_once(auto_tick) == 0:
                time.sleep(settings.worker_poll_seconds)
        except Exception:
            log.exception("worker iteration failed")
            time.sleep(2)
    log_event(log, "worker stopped")


if __name__ == "__main__":
    main()
