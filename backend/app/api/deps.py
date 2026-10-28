"""Authentication, CSRF protection, ownership checks and pagination helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from fastapi import Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.core.security import token_hash
from app.db.session import get_db
from app.models import AuthSession, User

SESSION_COOKIE = "nq_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "nexus"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

M = TypeVar("M")


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token, via_cookie = None, False
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    elif request.cookies.get(SESSION_COOKIE):
        token, via_cookie = request.cookies[SESSION_COOKIE], True
    if not token:
        raise ApiError(401, "unauthorized", "Please sign in.")
    if via_cookie and request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise ApiError(403, "csrf_failed", "Missing CSRF header.")
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    now = datetime.now(UTC)
    if sess is None or _as_aware(sess.expires_at) < now:
        raise ApiError(401, "unauthorized", "Your session has expired. Please sign in again.")
    user = db.get(User, sess.user_id)
    if user is None or user.status != "active":
        raise ApiError(401, "unauthorized", "Account is not active.")
    if now - _as_aware(sess.last_seen_at) > timedelta(minutes=5):
        sess.last_seen_at = now
        db.commit()
    request.state.user_id = user.id
    return user


def get_owned(db: Session, model: type[M], obj_id: str, owner_id: str, what: str) -> M:
    """Return the object if the user owns it, otherwise 404 (no hint that it exists)."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "owner_id", None) != owner_id:
        raise not_found(what)
    return obj


class Pagination:
    def __init__(self, limit: int = Query(25, ge=1), offset: int = Query(0, ge=0)) -> None:
        self.limit = min(limit, get_settings().max_page_size)
        self.offset = offset


def paginate(db: Session, stmt: Any, page: Pagination) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.limit(page.limit).offset(page.offset)))
    return items, int(total)
