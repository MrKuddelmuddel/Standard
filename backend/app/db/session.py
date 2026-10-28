from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            path = url.removeprefix("sqlite:///")
            if path and path != ":memory:" and os.path.dirname(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(conn, _):
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()

        _factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def reset_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine, _factory = None, None


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _factory is not None
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()
