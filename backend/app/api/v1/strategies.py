from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, current_user, get_owned, paginate
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import BacktestRun, Strategy, StrategyVersion, User
from app.schemas import Page, StrategyCreate, StrategyImport, StrategyOut, StrategyUpdate, ValidateRequest, VersionOut
from app.services import strategies as svc
from app.services.audit import audit
from quant.strategy_schema import (
    SCHEMA_VERSION,
    SUPPORTED_INDICATORS,
    SUPPORTED_SYMBOLS,
    SUPPORTED_TIMEFRAMES,
    validate_definition,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/schema")
def schema_info() -> dict:
    from quant.strategy_schema.model import StrategyDefinition

    return {
        "schema_version": SCHEMA_VERSION,
        "indicators": SUPPORTED_INDICATORS,
        "symbols": list(SUPPORTED_SYMBOLS),
        "timeframes": list(SUPPORTED_TIMEFRAMES),
        "operators": ["gt", "lt", "gte", "lte", "crosses_above", "crosses_below", "all", "any", "not"],
        "json_schema": StrategyDefinition.model_json_schema(by_alias=True),
    }


@router.post("/validate")
def validate(body: ValidateRequest, _: User = Depends(current_user)) -> dict:
    defn, issues = validate_definition(body.definition)
    if defn is None:
        return {"valid": False, "issues": [i.to_dict() for i in issues]}
    from quant.strategy_schema import canonical_hash

    return {
        "valid": True,
        "issues": [],
        "canonical_hash": canonical_hash(defn),
        "warmup_bars": defn.warmup_bars(),
        "definition": defn.model_dump(mode="json", by_alias=True),
    }


@router.get("", response_model=Page[StrategyOut])
def list_strategies(
    page: Pagination = Depends(),
    status: str = Query("active", pattern="^(active|archived|all)$"),
    q: str | None = Query(None, max_length=80),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Strategy).where(Strategy.owner_id == user.id)
    if status != "all":
        stmt = stmt.where(Strategy.status == status)
    if q:
        stmt = stmt.where(Strategy.name.ilike(f"%{q}%"))
    items, total = paginate(db, stmt.order_by(Strategy.updated_at.desc()), page)
    return {
        "items": [svc.strategy_payload(db, s) for s in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.post("", response_model=StrategyOut, status_code=201)
def create(body: StrategyCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    s = svc.create_strategy(db, user.id, body.name, body.description, body.definition)
    db.commit()
    return svc.strategy_payload(db, s)


@router.post("/import", response_model=StrategyOut, status_code=201)
def import_strategy(body: StrategyImport, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    s = svc.import_document(db, user.id, body.document)
    db.commit()
    return svc.strategy_payload(db, s)


@router.get("/{strategy_id}", response_model=StrategyOut)
def get(strategy_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return svc.strategy_payload(db, get_owned(db, Strategy, strategy_id, user.id, "Strategy"))


@router.patch("/{strategy_id}", response_model=StrategyOut)
def update(
    strategy_id: str, body: StrategyUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    s = get_owned(db, Strategy, strategy_id, user.id, "Strategy")
    if s.status == "archived":
        raise ApiError(409, "archived", "Archived strategies cannot be edited. Restore it first.")
    if body.name is not None:
        s.name = body.name.strip()
    if body.description is not None:
        s.description = body.description
    if body.definition is not None:
        svc.add_version(db, s, body.definition, user.id, body.note)
    db.commit()
    return svc.strategy_payload(db, s)


@router.post("/{strategy_id}/duplicate", response_model=StrategyOut, status_code=201)
def duplicate(strategy_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    s = get_owned(db, Strategy, strategy_id, user.id, "Strategy")
    v = db.get(StrategyVersion, s.current_version_id) if s.current_version_id else None
    if v is None:
        raise ApiError(409, "no_version", "Strategy has no version to duplicate.")
    copy = svc.create_strategy(
        db,
        user.id,
        f"{s.name} (copy)"[:80],
        s.description,
        v.definition_json,
        origin=s.origin,
        note=f"Duplicated from {s.id} v{v.version_number}",
    )
    db.commit()
    return svc.strategy_payload(db, copy)


@router.post("/{strategy_id}/archive", response_model=StrategyOut)
def archive(
    strategy_id: str, restore: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    s = get_owned(db, Strategy, strategy_id, user.id, "Strategy")
    s.status = "active" if restore else "archived"
    audit(db, user.id, "strategy.restored" if restore else "strategy.archived", "strategy", s.id)
    db.commit()
    return svc.strategy_payload(db, s)


@router.get("/{strategy_id}/versions", response_model=list[VersionOut])
def versions(
    strategy_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[StrategyVersion]:
    get_owned(db, Strategy, strategy_id, user.id, "Strategy")
    return list(
        db.scalars(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version_number.desc())
        )
    )


@router.get("/{strategy_id}/export")
def export(
    strategy_id: str, version_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    s = get_owned(db, Strategy, strategy_id, user.id, "Strategy")
    v = db.get(StrategyVersion, version_id or s.current_version_id or "")
    if v is None or v.strategy_id != s.id:
        raise ApiError(404, "not_found", "Version not found.")
    return svc.export_document(s, v)


@router.get("/{strategy_id}/backtests")
def strategy_backtests(
    strategy_id: str, page: Pagination = Depends(), user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    get_owned(db, Strategy, strategy_id, user.id, "Strategy")
    stmt = (
        select(BacktestRun)
        .join(StrategyVersion, StrategyVersion.id == BacktestRun.strategy_version_id)
        .where(StrategyVersion.strategy_id == strategy_id, BacktestRun.owner_id == user.id)
        .order_by(BacktestRun.created_at.desc())
    )
    items, total = paginate(db, stmt, page)
    numbers = {
        v.id: v.version_number
        for v in db.scalars(select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id))
    }
    return {
        "items": [
            {
                "id": b.id,
                "status": b.status,
                "created_at": b.created_at,
                "version_number": numbers.get(b.strategy_version_id),
                "strategy_version_id": b.strategy_version_id,
                "is_synthetic_data": b.is_synthetic_data,
                "metrics": (b.result_json or {}).get("metrics"),
                "error_message": b.error_message,
            }
            for b in items
        ],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }
