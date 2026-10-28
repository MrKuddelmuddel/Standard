from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, current_user, get_owned, paginate
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models import (
    BacktestRun,
    BacktestTrade,
    DiscoveryCandidate,
    DiscoveryJob,
    Strategy,
    StrategyVersion,
    User,
    ValidationRun,
)
from app.schemas import (
    BacktestCreate,
    BacktestOut,
    CandidateOut,
    DiscoveryCreate,
    DiscoveryOut,
    StrategyOut,
    TradeOut,
    ValidationCreate,
    ValidationOut,
)
from app.services import jobs
from app.services import runs as svc
from app.services.strategies import create_strategy, strategy_payload

router = APIRouter(tags=["runs"])


def _bt_payload(db: Session, b: BacktestRun, full: bool) -> dict[str, Any]:
    data = BacktestOut.model_validate(b).model_dump()
    v = db.get(StrategyVersion, b.strategy_version_id)
    s = db.get(Strategy, v.strategy_id) if v else None
    data["strategy"] = {"id": s.id, "name": s.name, "version_number": v.version_number} if s and v else None
    data["job"] = jobs.job_payload(jobs.latest_job(db, b.id))
    data["metrics"] = (b.result_json or {}).get("metrics")
    if full:
        data["result"] = b.result_json
    return data


# ------------------------------------------------------------------ backtests
@router.post("/backtests", status_code=202)
def create_backtest(body: BacktestCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    if not body.strategy_version_id:
        raise ApiError(422, "validation_error", "strategy_version_id is required.")
    run = svc.create_backtest(
        db,
        user.id,
        body.strategy_version_id,
        body.market_data_source_id,
        body.initial_capital,
        body.start_time,
        body.end_time,
        body.fee_bps,
        body.slippage_bps,
    )
    db.commit()
    job = jobs.latest_job(db, run.id)
    if job:
        jobs.after_commit(job.id)
    db.expire_all()
    return _bt_payload(db, db.get(BacktestRun, run.id), True)  # type: ignore[arg-type]


@router.post("/strategies/{strategy_id}/backtests", status_code=202)
def create_backtest_for_strategy(
    strategy_id: str, body: BacktestCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    s = get_owned(db, Strategy, strategy_id, user.id, "Strategy")
    body.strategy_version_id = body.strategy_version_id or s.current_version_id
    return create_backtest(body, user, db)


@router.get("/backtests")
def list_backtests(
    page: Pagination = Depends(), user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    items, total = paginate(
        db, select(BacktestRun).where(BacktestRun.owner_id == user.id).order_by(BacktestRun.created_at.desc()), page
    )
    return {
        "items": [_bt_payload(db, b, False) for b in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/backtests/{run_id}")
def get_backtest(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _bt_payload(db, get_owned(db, BacktestRun, run_id, user.id, "Backtest"), True)


@router.get("/backtests/{run_id}/trades")
def backtest_trades(
    run_id: str, page: Pagination = Depends(), user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    get_owned(db, BacktestRun, run_id, user.id, "Backtest")
    stmt = select(BacktestTrade).where(BacktestTrade.backtest_run_id == run_id).order_by(BacktestTrade.sequence)
    items, total = paginate(db, stmt, page)
    return {
        "items": [TradeOut.model_validate(t).model_dump() for t in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/backtests/{run_id}/metrics")
def backtest_metrics(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    b = get_owned(db, BacktestRun, run_id, user.id, "Backtest")
    if b.status != "completed":
        raise ApiError(409, "not_available", f"Metrics are not available: backtest is {b.status}.")
    return {"backtest_id": b.id, "metrics": svc.metrics_of(db, b.id)}


@router.post("/backtests/{run_id}/cancel")
def cancel_backtest(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    get_owned(db, BacktestRun, run_id, user.id, "Backtest")
    job = svc.cancel_job_for(db, user.id, run_id)
    db.commit()
    return jobs.job_payload(job) or {}


# ------------------------------------------------------------------ validations
@router.post("/validations", status_code=202, response_model=ValidationOut)
def create_validation(
    body: ValidationCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> ValidationRun:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    v = svc.create_validation(db, user.id, body)
    db.commit()
    job = jobs.latest_job(db, v.id)
    if job:
        jobs.after_commit(job.id)
    db.expire_all()
    return db.get(ValidationRun, v.id)  # type: ignore[return-value]


@router.get("/validations", response_model=list[ValidationOut])
def list_validations(
    strategy_version_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list:
    stmt = select(ValidationRun).where(ValidationRun.owner_id == user.id)
    if strategy_version_id:
        stmt = stmt.where(ValidationRun.strategy_version_id == strategy_version_id)
    return list(db.scalars(stmt.order_by(ValidationRun.created_at.desc()).limit(50)))


@router.get("/validations/{validation_id}", response_model=ValidationOut)
def get_validation(
    validation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> ValidationRun:
    return get_owned(db, ValidationRun, validation_id, user.id, "Validation")


# ------------------------------------------------------------------ discovery
def _disc_payload(db: Session, d: DiscoveryJob) -> dict[str, Any]:
    data = DiscoveryOut.model_validate(d).model_dump()
    data["job"] = jobs.job_payload(jobs.latest_job(db, d.id))
    return data


@router.post("/discoveries", status_code=202)
def create_discovery(body: DiscoveryCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    d = svc.create_discovery(db, user.id, body.market_data_source_id, body.config)
    db.commit()
    job = jobs.latest_job(db, d.id)
    if job:
        jobs.after_commit(job.id)
    db.expire_all()
    return _disc_payload(db, db.get(DiscoveryJob, d.id))  # type: ignore[arg-type]


@router.get("/discoveries")
def list_discoveries(
    page: Pagination = Depends(), user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    items, total = paginate(
        db, select(DiscoveryJob).where(DiscoveryJob.owner_id == user.id).order_by(DiscoveryJob.created_at.desc()), page
    )
    return {"items": [_disc_payload(db, d) for d in items], "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/discoveries/{discovery_id}")
def get_discovery(discovery_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _disc_payload(db, get_owned(db, DiscoveryJob, discovery_id, user.id, "Discovery job"))


@router.get("/discoveries/{discovery_id}/candidates")
def candidates(
    discovery_id: str,
    status: str | None = None,
    sort: str = "score",
    page: Pagination = Depends(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    get_owned(db, DiscoveryJob, discovery_id, user.id, "Discovery job")
    stmt = select(DiscoveryCandidate).where(DiscoveryCandidate.discovery_job_id == discovery_id)
    if status:
        stmt = stmt.where(DiscoveryCandidate.status == status)
    if sort not in ("score", "name"):
        raise ApiError(422, "invalid_sort", "sort must be 'score' or 'name'.")
    order = DiscoveryCandidate.score.desc().nulls_last() if sort == "score" else DiscoveryCandidate.name.asc()
    items, total = paginate(db, stmt.order_by(order, DiscoveryCandidate.name), page)
    return {
        "items": [CandidateOut.model_validate(c).model_dump() for c in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.post("/discoveries/{discovery_id}/cancel")
def cancel_discovery(discovery_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    get_owned(db, DiscoveryJob, discovery_id, user.id, "Discovery job")
    job = svc.cancel_job_for(db, user.id, discovery_id)
    db.commit()
    return jobs.job_payload(job) or {}


@router.post("/discoveries/{discovery_id}/candidates/{candidate_id}/save", status_code=201, response_model=StrategyOut)
def save_candidate(
    discovery_id: str, candidate_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    get_owned(db, DiscoveryJob, discovery_id, user.id, "Discovery job")
    c = db.get(DiscoveryCandidate, candidate_id)
    if c is None or c.discovery_job_id != discovery_id:
        raise ApiError(404, "not_found", "Candidate not found.")
    if c.strategy_version_id:
        raise ApiError(409, "already_saved", "This candidate was already saved as a strategy.")
    s = create_strategy(
        db,
        user.id,
        c.name,
        f"Saved from discovery job {discovery_id}. Status: {c.status}. Flags: {', '.join(c.flags) or 'none'}.",
        c.definition_json,
        origin="discovery",
        note=f"Discovery candidate {c.candidate_hash[:12]}",
    )
    db.flush()
    c.strategy_version_id = s.current_version_id
    db.commit()
    return strategy_payload(db, s)
