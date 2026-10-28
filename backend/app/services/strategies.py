"""Strategy CRUD with immutable versions, import/export in a documented JSON format."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import BacktestRun, Strategy, StrategyVersion
from app.services.audit import audit
from quant.strategy_schema import canonical_hash, validate_definition

EXPORT_FORMAT = "nexus-quant-strategy"
EXPORT_FORMAT_VERSION = 1


def parse_definition(data: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    """Validate and return (canonical definition dict, hash, schema_version) or raise a 422 with issues."""
    defn, issues = validate_definition(data)
    if defn is None:
        raise ApiError(422, "invalid_strategy", "The strategy definition is invalid.", [i.to_dict() for i in issues])
    return defn.model_dump(mode="json", by_alias=True), canonical_hash(defn), defn.schema_version


def _next_version_number(db: Session, strategy_id: str) -> int:
    return (
        int(
            db.scalar(
                select(func.max(StrategyVersion.version_number)).where(StrategyVersion.strategy_id == strategy_id)
            )
            or 0
        )
        + 1
    )


def add_version(
    db: Session, strategy: Strategy, definition: dict[str, Any], user_id: str, note: str = ""
) -> StrategyVersion:
    canonical, h, schema_version = parse_definition(definition)
    current = db.get(StrategyVersion, strategy.current_version_id) if strategy.current_version_id else None
    if current is not None and current.canonical_hash == h:
        return current
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=_next_version_number(db, strategy.id),
        schema_version=schema_version,
        definition_json=canonical,
        canonical_hash=h,
        note=note,
        created_by=user_id,
    )
    db.add(version)
    db.flush()
    strategy.current_version_id = version.id
    audit(
        db, user_id, "strategy.version_created", "strategy", strategy.id, {"version": version.version_number, "hash": h}
    )
    return version


def create_strategy(
    db: Session,
    owner_id: str,
    name: str,
    description: str,
    definition: dict[str, Any],
    origin: str = "manual",
    note: str = "",
) -> Strategy:
    definition = {**definition, "name": definition.get("name") or name}
    parse_definition(definition)  # fail before creating rows
    strategy = Strategy(owner_id=owner_id, name=name, description=description, origin=origin)
    db.add(strategy)
    db.flush()
    add_version(db, strategy, definition, owner_id, note or "Initial version")
    audit(db, owner_id, "strategy.created", "strategy", strategy.id, {"origin": origin})
    return strategy


def strategy_payload(db: Session, s: Strategy) -> dict[str, Any]:
    version = db.get(StrategyVersion, s.current_version_id) if s.current_version_id else None
    count = db.scalar(select(func.count()).where(StrategyVersion.strategy_id == s.id)) or 0
    last = db.scalar(
        select(BacktestRun)
        .join(StrategyVersion, StrategyVersion.id == BacktestRun.strategy_version_id)
        .where(StrategyVersion.strategy_id == s.id)
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    )
    return {
        **{
            k: getattr(s, k)
            for k in ("id", "name", "description", "origin", "status", "current_version_id", "created_at", "updated_at")
        },
        "current_version": version,
        "version_count": int(count),
        "last_backtest": {
            "id": last.id,
            "status": last.status,
            "created_at": last.created_at,
            "net_return": (last.result_json or {}).get("metrics", {}).get("net_return"),
        }
        if last
        else None,
    }


def export_document(s: Strategy, v: StrategyVersion) -> dict[str, Any]:
    return {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "strategy": {
            "name": s.name,
            "description": s.description,
            "version_number": v.version_number,
            "canonical_hash": v.canonical_hash,
        },
        "definition": v.definition_json,
    }


def import_document(db: Session, owner_id: str, doc: dict[str, Any]) -> Strategy:
    if doc.get("format") != EXPORT_FORMAT or doc.get("format_version") != EXPORT_FORMAT_VERSION:
        raise ApiError(422, "invalid_import", f"Expected format '{EXPORT_FORMAT}' version {EXPORT_FORMAT_VERSION}.")
    meta = doc.get("strategy") or {}
    definition = doc.get("definition")
    if not isinstance(definition, dict):
        raise ApiError(422, "invalid_import", "Field 'definition' must be an object.")
    name = str(meta.get("name") or definition.get("name") or "Imported strategy")[:80]
    description = str(meta.get("description") or "")[:2000]
    return create_strategy(db, owner_id, name, description, definition, origin="imported", note="Imported")
