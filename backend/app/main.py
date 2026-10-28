"""NEXUS QUANT API. Analysis, backtesting and simulation only: no real orders, no exchange keys."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import activity, auth, market_data, runs, strategies
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import log_event, request_id_var, setup_logging
from app.db.session import get_engine, session_scope
from app.services import runs as _runs  # noqa: F401  (registers job handlers)
from app.services.ai import agent as _agent  # noqa: F401  (registers job handlers)
from quant import ENGINE_VERSION, EXECUTION_MODEL_VERSION

log = logging.getLogger("nexus.api")
API_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    if settings.is_sqlite and settings.nexus_env != "prod":
        from app.db.base import Base

        Base.metadata.create_all(get_engine())  # dev convenience; production uses Alembic migrations
    worker = None
    if settings.jobs_mode == "thread":
        from app.services.jobs import WorkerThread
        from app.services.paper import auto_tick

        worker = WorkerThread(tick=auto_tick)
        worker.start()
    log_event(log, "api started", env=settings.nexus_env, jobs_mode=settings.jobs_mode, ai=settings.ai_configured)
    yield
    if worker:
        worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NEXUS QUANT API",
        version=API_VERSION,
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/docs" if settings.nexus_env != "prod" else None,
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-requested-with", "authorization"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # noqa: ANN001
        rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
        request_id_var.set(rid)
        start = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["x-request-id"] = rid
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["cache-control"] = response.headers.get("cache-control", "no-store")
        if not request.url.path.startswith("/api/docs"):
            response.headers["content-security-policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.cookie_secure:
            response.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
        log_event(
            log,
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response

    @app.get("/api/v1/health", tags=["health"])
    def health() -> dict:
        db_ok = True
        try:
            with session_scope() as db:
                db.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "unavailable",
            "api_version": API_VERSION,
            "engine_version": ENGINE_VERSION,
            "execution_model": EXECUTION_MODEL_VERSION,
            "jobs_mode": settings.jobs_mode,
            "ai_configured": settings.ai_configured,
            "live_trading": False,
        }

    for r in (auth.router, strategies.router, market_data.router, runs.router, activity.router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
