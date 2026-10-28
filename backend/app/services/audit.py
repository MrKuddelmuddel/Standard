from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import redact
from app.models import AuditLog


def audit(
    db: Session,
    owner_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Record a security- or history-relevant action. Secrets in `detail` are redacted."""
    db.add(
        AuditLog(
            owner_id=owner_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=redact(detail or {}),
            ip=ip,
        )
    )
