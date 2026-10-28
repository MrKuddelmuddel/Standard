"""Backtests, validations and discovery jobs: creation (bound to exact inputs) and background execution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.models import (
    BacktestMetric,
    BacktestRun,
    BacktestTrade,
    DiscoveryCandidate,
    DiscoveryJob,
    Job,
    MarketDataSource,
    Strategy,
    StrategyVersion,
    ValidationRun,
)
from app.services import jobs
from app.services.audit import audit
from app.services.market_data import get_source, load_series
from quant import ENGINE_VERSION, EXECUTION_MODEL_VERSION
from quant.discovery import RANKING_VERSION, SearchConfig, run_discovery
from quant.engine import BacktestError, run_backtest
from quant.strategy_schema import StrategyDefinition
from quant.validation import run_validation

MAX_CURVE_POINTS = 1_500


def owned_version(db: Session, version_id: str, owner_id: str) -> tuple[StrategyVersion, Strategy]:
    v = db.get(StrategyVersion, version_id)
    s = db.get(Strategy, v.strategy_id) if v else None
    if v is None or s is None or s.owner_id != owner_id:
        raise not_found("Strategy version")
    return v, s


def _check_compat(defn: StrategyDefinition, src: MarketDataSource) -> None:
    if src.timeframe != defn.timeframe:
        raise ApiError(422, "timeframe_mismatch", f"Strategy uses {defn.timeframe}, data source is {src.timeframe}.")
    if src.symbol not in defn.symbols:
        raise ApiError(
            422, "symbol_mismatch", f"Strategy trades {', '.join(defn.symbols)}, data source is {src.symbol}."
        )
    if src.row_count == 0:
        raise ApiError(422, "no_data", "The data source has no candles.")
    if src.row_count > get_settings().max_backtest_bars:
        raise ApiError(
            413,
            "too_many_bars",
            f"Data source has {src.row_count} candles, limit is {get_settings().max_backtest_bars}.",
        )


def downsample(times: np.ndarray, *series: np.ndarray, points: int = MAX_CURVE_POINTS) -> list[list[float]]:
    """Keep the shape of curves for charts: pick evenly spaced points plus the minimum of each bucket."""
    n = len(times)
    if n == 0:
        return []
    if n <= points:
        idx = np.arange(n)
    else:
        buckets = np.array_split(np.arange(n), points)
        idx = np.unique(np.concatenate([[b[0], b[np.argmin(series[-1][b])]] for b in buckets] + [[n - 1]]))
    return [[int(times[i]), *[round(float(s[i]), 6) for s in series]] for i in idx]


# ----------------------------------------------------------------------------- backtests
def create_backtest(
    db: Session,
    owner_id: str,
    version_id: str,
    source_id: str,
    capital: float,
    start_time: int | None,
    end_time: int | None,
    fee_bps: float | None,
    slippage_bps: float | None,
) -> BacktestRun:
    version, _ = owned_version(db, version_id, owner_id)
    src = get_source(db, source_id, owner_id)
    defn = StrategyDefinition.model_validate(version.definition_json)
    _check_compat(defn, src)
    fee = defn.costs.fee_bps if fee_bps is None else fee_bps
    slip = defn.costs.slippage_bps if slippage_bps is None else slippage_bps
    run = BacktestRun(
        owner_id=owner_id,
        strategy_version_id=version.id,
        market_data_source_id=src.id,
        data_revision=src.revision,
        data_fingerprint=src.fingerprint,
        start_time=start_time,
        end_time=end_time,
        initial_capital=capital,
        fee_model={"type": "bps_of_notional_per_fill", "fee_bps": fee},
        slippage_model={"type": "fixed_bps_adverse", "slippage_bps": slip, "applies_to": "market and stop fills"},
        execution_model_version=EXECUTION_MODEL_VERSION,
        engine_version=ENGINE_VERSION,
        config_json={"requested_start_time": start_time, "requested_end_time": end_time, "intrabar_rule": "stop_first"},
        is_synthetic_data=src.is_synthetic,
    )
    db.add(run)
    db.flush()
    jobs.enqueue(db, owner_id, "backtest", run.id)
    audit(db, owner_id, "backtest.created", "backtest_run", run.id, {"version": version.id, "source": src.id})
    return run


def _execute_backtest(db: Session, job: Job, ctx: jobs.JobContext) -> None:
    run = db.get(BacktestRun, job.target_id)
    assert run is not None
    run.status, run.started_at = "running", datetime.now(UTC)
    db.commit()
    src = db.get(MarketDataSource, run.market_data_source_id)
    version = db.get(StrategyVersion, run.strategy_version_id)
    assert src is not None and version is not None
    if src.revision != run.data_revision or src.fingerprint != run.data_fingerprint:
        raise jobs.JobFailure(
            "data_changed", "The data source changed after the backtest was created. Start a new backtest."
        )
    series = load_series(db, src)
    defn = StrategyDefinition.model_validate(version.definition_json)
    start_idx = int(np.searchsorted(series.open_time, run.start_time)) if run.start_time else None
    end_idx = int(np.searchsorted(series.open_time, run.end_time, side="right")) if run.end_time else None
    try:
        res = run_backtest(
            series,
            defn,
            run.initial_capital,
            start_index=start_idx,
            end_index=end_idx,
            fee_bps=run.fee_model["fee_bps"],
            slippage_bps=run.slippage_model["slippage_bps"],
        )
    except BacktestError as exc:
        raise jobs.JobFailure(exc.code, str(exc)) from exc
    if ctx.cancelled():
        raise jobs.JobFailure("cancelled", "Cancelled by user.")
    for t in res.trades:
        db.add(
            BacktestTrade(
                backtest_run_id=run.id,
                sequence=t["sequence"],
                side=t["side"],
                entry_time=t["entry_time"],
                exit_time=t["exit_time"],
                entry_price=t["entry_price"],
                exit_price=t["exit_price"],
                quantity=t["quantity"],
                gross_pnl=t["gross_pnl"],
                fees=t["fees"],
                slippage_cost=t["slippage_cost"],
                funding_cost=t["funding_cost"],
                net_pnl=t["net_pnl"],
                exit_reason=t["exit_reason"],
                meta={
                    k: t[k]
                    for k in ("bars_held", "stop", "target", "r_multiple", "return_pct", "entry_index", "exit_index")
                },
            )
        )
    for name, value in res.metrics.items():
        db.add(
            BacktestMetric(
                backtest_run_id=run.id, metric_name=name, metric_value=value, note=res.metric_notes.get(name)
            )
        )
    for name, note in res.metric_notes.items():
        if name not in res.metrics:
            db.add(BacktestMetric(backtest_run_id=run.id, metric_name=name, metric_value=None, note=note))
    run.start_time, run.end_time = res.config["start_time"], res.config["end_time"]
    run.config_json = {**run.config_json, **res.config}
    run.result_json = {
        "metrics": res.metrics,
        "metric_notes": res.metric_notes,
        "warnings": res.warnings,
        "curve": downsample(res.times, res.equity, res.drawdown),
        "curve_columns": ["time", "equity", "drawdown"],
    }
    run.status, run.completed_at = "completed", datetime.now(UTC)


def _fail_backtest(db: Session, job: Job, code: str, message: str) -> None:
    run = db.get(BacktestRun, job.target_id)
    if run:
        run.status = "cancelled" if code == "cancelled" else "failed"
        run.error_code, run.error_message, run.completed_at = code, message[:500], datetime.now(UTC)


def metrics_of(db: Session, run_id: str) -> dict[str, Any]:
    rows = db.scalars(select(BacktestMetric).where(BacktestMetric.backtest_run_id == run_id))
    return {r.metric_name: {"value": r.metric_value, "note": r.note} for r in rows}


# ----------------------------------------------------------------------------- validation
def create_validation(db: Session, owner_id: str, body: Any) -> ValidationRun:
    version, _ = owned_version(db, body.strategy_version_id, owner_id)
    src = get_source(db, body.market_data_source_id, owner_id)
    defn = StrategyDefinition.model_validate(version.definition_json)
    _check_compat(defn, src)
    if body.train_fraction + body.validation_fraction >= 0.95:
        raise ApiError(422, "invalid_split", "Train and validation must leave at least 5 % for the test segment.")
    v = ValidationRun(
        owner_id=owner_id,
        strategy_version_id=version.id,
        market_data_source_id=src.id,
        data_fingerprint=src.fingerprint,
        method="split+walk_forward+sensitivity_v1",
        configuration=body.model_dump(exclude={"strategy_version_id", "market_data_source_id"}),
        is_synthetic_data=src.is_synthetic,
    )
    db.add(v)
    db.flush()
    jobs.enqueue(db, owner_id, "validation", v.id)
    audit(db, owner_id, "validation.created", "validation_run", v.id)
    return v


def _execute_validation(db: Session, job: Job, ctx: jobs.JobContext) -> None:
    v = db.get(ValidationRun, job.target_id)
    assert v is not None
    v.status = "running"
    db.commit()
    src = db.get(MarketDataSource, v.market_data_source_id)
    version = db.get(StrategyVersion, v.strategy_version_id)
    assert src is not None and version is not None
    if src.fingerprint != v.data_fingerprint:
        raise jobs.JobFailure("data_changed", "The data source changed after the validation was created.")
    series = load_series(db, src)
    c = v.configuration
    try:
        rep = run_validation(
            series,
            StrategyDefinition.model_validate(version.definition_json),
            c["initial_capital"],
            train=c["train_fraction"],
            validation=c["validation_fraction"],
            folds=c["folds"],
            cost_multiplier=c["cost_multiplier"],
        )
    except BacktestError as exc:
        raise jobs.JobFailure(exc.code, str(exc)) from exc
    v.segments, v.metrics, v.warnings = rep.segments, rep.results, rep.warnings
    if series.synthetic:
        v.warnings = [*rep.warnings, "Synthetic demo data: results say nothing about real markets."]
    v.status, v.completed_at = "completed", datetime.now(UTC)


def _fail_validation(db: Session, job: Job, code: str, message: str) -> None:
    v = db.get(ValidationRun, job.target_id)
    if v:
        v.status = "cancelled" if code == "cancelled" else "failed"
        v.error_code, v.error_message, v.completed_at = code, message[:500], datetime.now(UTC)


# ----------------------------------------------------------------------------- discovery
def create_discovery(db: Session, owner_id: str, source_id: str, raw_config: dict[str, Any]) -> DiscoveryJob:
    src = get_source(db, source_id, owner_id)
    try:
        cfg = SearchConfig.model_validate({**raw_config, "symbol": src.symbol, "timeframe": src.timeframe})
    except ValueError as exc:
        raise ApiError(422, "invalid_search_config", "The search configuration is invalid.", str(exc)[:1000]) from exc
    s = get_settings()
    if cfg.max_candidates > s.max_discovery_candidates:
        raise ApiError(422, "limit_exceeded", f"max_candidates is limited to {s.max_discovery_candidates}.")
    cfg = cfg.model_copy(update={"max_seconds": min(cfg.max_seconds, s.max_discovery_seconds)})
    if src.row_count > s.max_backtest_bars:
        raise ApiError(413, "too_many_bars", "Data source is too large for discovery.")
    d = DiscoveryJob(
        owner_id=owner_id,
        market_data_source_id=src.id,
        data_fingerprint=src.fingerprint,
        search_config=cfg.model_dump(mode="json"),
        is_synthetic_data=src.is_synthetic,
    )
    db.add(d)
    db.flush()
    jobs.enqueue(db, owner_id, "discovery", d.id)
    audit(db, owner_id, "discovery.created", "discovery_job", d.id, {"max_candidates": cfg.max_candidates})
    return d


def _execute_discovery(db: Session, job: Job, ctx: jobs.JobContext) -> None:
    d = db.get(DiscoveryJob, job.target_id)
    assert d is not None
    d.status, d.started_at = "running", datetime.now(UTC)
    db.commit()
    src = db.get(MarketDataSource, d.market_data_source_id)
    assert src is not None
    if src.fingerprint != d.data_fingerprint:
        raise jobs.JobFailure("data_changed", "The data source changed after the job was created.")
    series = load_series(db, src)
    cfg = SearchConfig.model_validate(d.search_config)
    try:
        res = run_discovery(series, cfg, progress=ctx.progress, should_cancel=ctx.cancelled)
    except BacktestError as exc:
        raise jobs.JobFailure(exc.code, str(exc)) from exc
    for c in res.candidates:
        db.add(
            DiscoveryCandidate(
                discovery_job_id=d.id,
                template=c.template,
                name=str(c.definition.get("name", "candidate"))[:80],
                candidate_hash=c.hash or f"invalid-{id(c)}",
                definition_json=c.definition,
                status=c.status,
                rejection_reason=c.rejection_reason,
                metrics={
                    "train": c.train,
                    "validation": c.validation,
                    "test": c.test,
                    "validation_2x_costs": c.cost_stress,
                },
                flags=c.flags,
                score=c.score,
                score_parts=c.score_parts,
            )
        )
    d.candidate_count = len(res.candidates)
    d.report = {
        "generated": res.generated,
        "duplicates_removed": res.duplicates,
        "tested": res.tested,
        "stopped_early": res.stopped_early,
        "segments": res.segments,
        "ranking_version": RANKING_VERSION,
        "status_counts": {
            s: sum(1 for c in res.candidates if c.status == s) for s in ("rejected", "shortlisted", "validated")
        },
        "note": "Score uses validation metrics only. The test segment is evaluated once, for validated candidates only. "
        f"{res.tested} candidates were backtested, which raises the chance of lucky results.",
    }
    if res.stopped_early == "cancelled":
        raise jobs.JobFailure("cancelled", "Cancelled by user.")
    d.status, d.completed_at = "completed", datetime.now(UTC)
    if res.stopped_early == "time_limit":
        d.report["warning"] = "Stopped at the time limit. Not all candidates were tested."


def _fail_discovery(db: Session, job: Job, code: str, message: str) -> None:
    d = db.get(DiscoveryJob, job.target_id)
    if d:
        d.status = "cancelled" if code == "cancelled" else "failed"
        d.error_code, d.error_message, d.completed_at = code, message[:500], datetime.now(UTC)


def cancel_job_for(db: Session, owner_id: str, target_id: str) -> Job:
    job = jobs.latest_job(db, target_id)
    if job is None or job.owner_id != owner_id:
        raise not_found("Job")
    if job.status not in ("queued", "running"):
        raise ApiError(409, "not_cancellable", f"Job is already {job.status}.")
    job.cancel_requested = True
    if job.status == "queued":
        job.status, job.error_code, job.finished_at = "cancelled", "cancelled", datetime.now(UTC)
        _, on_fail = jobs.HANDLERS[job.kind]
        on_fail(db, job, "cancelled", "Cancelled before start.")
    audit(db, owner_id, "job.cancel_requested", job.kind, target_id)
    return job


jobs.register("backtest", _execute_backtest, _fail_backtest)
jobs.register("validation", _execute_validation, _fail_validation)
jobs.register("discovery", _execute_discovery, _fail_discovery)
