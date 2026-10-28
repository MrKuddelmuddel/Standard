"""Journal, paper trading, TradingView alerts, AI research and the overview."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, client_ip, current_user, get_owned, paginate
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models import (
    AgentRun,
    AgentToolCall,
    AuditLog,
    BacktestRun,
    DiscoveryJob,
    JournalTrade,
    MarketDataSource,
    PaperFill,
    PaperOrder,
    PaperSession,
    Strategy,
    TradingViewAlert,
    User,
    WebhookToken,
)
from app.schemas import (
    JournalImportRequest,
    JournalTradeIn,
    PaperAdvance,
    PaperCreate,
    ResearchConfirm,
    ResearchRequest,
)
from app.services import jobs
from app.services import journal as jsvc
from app.services import paper as psvc
from app.services import tradingview as tvsvc
from app.services.ai import agent as ai
from app.services.audit import audit

router = APIRouter()


# ============================================================================ journal
@router.get("/journal/trades", tags=["journal"])
def list_trades(
    page: Pagination = Depends(),
    symbol: str | None = None,
    side: str | None = Query(None, pattern="^(long|short)$"),
    source_type: str | None = None,
    strategy_id: str | None = None,
    tag: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    q: str | None = Query(None, max_length=80),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(JournalTrade).where(JournalTrade.owner_id == user.id)
    if symbol:
        stmt = stmt.where(JournalTrade.symbol == symbol.upper())
    if side:
        stmt = stmt.where(JournalTrade.side == side)
    if source_type:
        stmt = stmt.where(JournalTrade.source_type == source_type)
    if strategy_id:
        stmt = stmt.where(JournalTrade.strategy_id == strategy_id)
    if start:
        stmt = stmt.where(JournalTrade.entry_time >= start)
    if end:
        stmt = stmt.where(JournalTrade.entry_time <= end)
    if q:
        stmt = stmt.where(or_(JournalTrade.notes.ilike(f"%{q}%"), JournalTrade.setup.ilike(f"%{q}%")))
    all_matching = list(db.scalars(stmt))
    if tag:
        all_matching = [t for t in all_matching if tag in (t.tags or [])]
        ids = [t.id for t in all_matching]
        stmt = select(JournalTrade).where(JournalTrade.id.in_(ids)) if ids else stmt.where(JournalTrade.id == "")
    items, total = paginate(db, stmt.order_by(JournalTrade.entry_time.desc()), page)
    return {
        "items": [jsvc.to_out(t) for t in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
        "stats": jsvc.stats(all_matching),
    }


def _check_strategy(db: Session, owner_id: str, strategy_id: str | None) -> None:
    if strategy_id:
        get_owned(db, Strategy, strategy_id, owner_id, "Strategy")


@router.post("/journal/trades", status_code=201, tags=["journal"])
def create_trade(body: JournalTradeIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _check_strategy(db, user.id, body.strategy_id)
    t, dup = jsvc.create_trade(db, user.id, body)
    audit(db, user.id, "journal.trade_created", "journal_trade", None)
    db.commit()
    return {**jsvc.to_out(t), "duplicate_warning": dup}


@router.get("/journal/trades/{trade_id}", tags=["journal"])
def get_trade(trade_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return jsvc.to_out(get_owned(db, JournalTrade, trade_id, user.id, "Trade"))


@router.put("/journal/trades/{trade_id}", tags=["journal"])
def update_trade(
    trade_id: str, body: JournalTradeIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    t = get_owned(db, JournalTrade, trade_id, user.id, "Trade")
    _check_strategy(db, user.id, body.strategy_id)
    if body.exit_time and body.exit_time < body.entry_time:
        raise ApiError(422, "invalid_trade", "Exit time is before entry time.")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    t.dedupe_key = jsvc.dedupe_key(user.id, t.symbol, t.side, body.entry_time, t.entry_price, t.quantity)
    db.commit()
    return jsvc.to_out(t)


@router.delete("/journal/trades/{trade_id}", status_code=204, tags=["journal"])
def delete_trade(trade_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    t = get_owned(db, JournalTrade, trade_id, user.id, "Trade")
    if t.source_type == "paper":
        raise ApiError(409, "protected", "Paper trades are part of a session history and cannot be deleted.")
    db.delete(t)
    audit(db, user.id, "journal.trade_deleted", "journal_trade", trade_id)
    db.commit()


@router.post("/journal/imports/preview", tags=["journal"])
def import_preview(
    body: JournalImportRequest, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    preview = jsvc.parse_csv(db, user.id, body.content, body.mapping)
    preview["rows"] = preview["rows"][:200]
    preview["fields"] = jsvc.FIELDS
    preview["required"] = jsvc.REQUIRED
    return preview


@router.post("/journal/imports", status_code=201, tags=["journal"])
def import_commit(
    body: JournalImportRequest, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    res = jsvc.commit_csv(db, user.id, body.filename, body.content, body.mapping, body.skip_duplicates)
    db.commit()
    return res


# ============================================================================ paper trading
@router.post("/paper/sessions", status_code=201, tags=["paper"])
def create_session(body: PaperCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sess = psvc.create_session(db, user.id, body)
    db.commit()
    return psvc.session_payload(db, sess)


@router.get("/paper/sessions", tags=["paper"])
def list_sessions(
    page: Pagination = Depends(), user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    items, total = paginate(
        db, select(PaperSession).where(PaperSession.owner_id == user.id).order_by(PaperSession.created_at.desc()), page
    )
    return {
        "items": [psvc.session_payload(db, s) for s in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/paper/sessions/{session_id}", tags=["paper"])
def get_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sess = get_owned(db, PaperSession, session_id, user.id, "Paper session")
    orders = list(
        db.scalars(
            select(PaperOrder).where(PaperOrder.session_id == sess.id).order_by(PaperOrder.bar_time.desc()).limit(200)
        )
    )
    fills = list(
        db.scalars(
            select(PaperFill).where(PaperFill.session_id == sess.id).order_by(PaperFill.bar_time.desc()).limit(200)
        )
    )
    events = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "paper_session", AuditLog.entity_id == sess.id)
            .order_by(AuditLog.created_at.desc())
            .limit(50)
        )
    )
    return {
        **psvc.session_payload(db, sess),
        "equity_curve": sess.equity_curve,
        "orders": [
            {
                c: getattr(o, c)
                for c in ("id", "bar_time", "side", "intent", "order_type", "quantity", "status", "reason")
            }
            for o in orders
        ],
        "fills": [
            {c: getattr(f, c) for c in ("id", "order_id", "bar_time", "price", "ref_price", "quantity", "fee")}
            for f in fills
        ],
        "audit": [{"action": e.action, "created_at": e.created_at} for e in events],
    }


@router.post("/paper/sessions/{session_id}/advance", tags=["paper"])
def session_advance(
    session_id: str, body: PaperAdvance, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    get_owned(db, PaperSession, session_id, user.id, "Paper session")
    try:
        res = psvc.advance(db, session_id, body.bars)
        db.commit()
    except ApiError:
        db.commit()  # persist a forced stop on data change
        raise
    sess = db.get(PaperSession, session_id)
    return {**res, "session": psvc.session_payload(db, sess)}  # type: ignore[arg-type]


@router.post("/paper/sessions/{session_id}/{action}", tags=["paper"])
def session_action(
    session_id: str, action: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    if action not in psvc.TRANSITIONS:
        raise ApiError(404, "not_found", "Unknown action.")
    sess = get_owned(db, PaperSession, session_id, user.id, "Paper session")
    psvc.transition(db, sess, action, user.id)
    db.commit()
    return psvc.session_payload(db, sess)


# ============================================================================ tradingview
@router.post("/tradingview/webhook", status_code=201, tags=["tradingview"])
def webhook(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    limiter.check(f"webhook:{client_ip(request)}", s.webhook_requests_per_minute)
    secret = str(payload.get("secret", ""))
    if secret:
        limiter.check(f"webhook-token:{secret[-8:]}", s.webhook_requests_per_minute)
    alert = tvsvc.receive(db, payload)
    db.commit()
    return {"id": alert.id, "status": alert.status, "note": "Stored. No orders are executed."}


@router.post("/tradingview/token", tags=["tradingview"])
def rotate_token(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    token = tvsvc.create_token(db, user.id)
    db.commit()
    return {
        "secret": token,
        "note": "Shown once. Put it into the 'secret' field of your alert message.",
        "example_payload": tvsvc.EXAMPLE_PAYLOAD,
    }


@router.get("/tradingview/alerts", tags=["tradingview"])
def alerts(page: Pagination = Depends(), user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    items, total = paginate(
        db,
        select(TradingViewAlert)
        .where(TradingViewAlert.owner_id == user.id)
        .order_by(TradingViewAlert.received_at.desc()),
        page,
    )
    tok = db.scalar(select(WebhookToken).where(WebhookToken.owner_id == user.id, WebhookToken.revoked.is_(False)))
    return {
        "items": [
            {
                c: getattr(a, c)
                for c in (
                    "id",
                    "event_id",
                    "symbol",
                    "action",
                    "price",
                    "alert_time",
                    "status",
                    "journal_trade_id",
                    "received_at",
                    "payload",
                )
            }
            for a in items
        ],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
        "token": {
            "active": tok is not None,
            "hint": tok.hint if tok else None,
            "last_used_at": tok.last_used_at if tok else None,
        },
        "example_payload": tvsvc.EXAMPLE_PAYLOAD,
    }


@router.post("/tradingview/alerts/{alert_id}/journal", status_code=201, tags=["tradingview"])
def alert_to_journal(
    alert_id: str,
    quantity: float = Body(..., embed=True, gt=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    alert = get_owned(db, TradingViewAlert, alert_id, user.id, "Alert")
    trade = tvsvc.link_to_journal(db, user.id, alert, quantity)
    db.commit()
    return jsvc.to_out(trade)


# ============================================================================ AI
def _run_payload(db: Session, r: AgentRun, calls: bool) -> dict[str, Any]:
    data = {c.name: getattr(r, c.name) for c in AgentRun.__table__.columns if c.name != "owner_id"}
    data["job"] = jobs.job_payload(jobs.latest_job(db, r.id))
    if calls:
        data["tool_calls"] = [
            {
                c: getattr(t, c)
                for c in ("sequence", "tool_name", "arguments", "result", "is_error", "duration_ms", "created_at")
            }
            for t in db.scalars(
                select(AgentToolCall).where(AgentToolCall.agent_run_id == r.id).order_by(AgentToolCall.sequence)
            )
        ]
    return data


@router.get("/ai/status", tags=["ai"])
def ai_status(_: User = Depends(current_user)) -> dict:
    return ai.ai_status()


@router.post("/ai/research", status_code=202, tags=["ai"])
def research(body: ResearchRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    run = ai.start_research(db, user.id, body.task, body.symbol, body.timeframe)
    db.commit()
    job = jobs.latest_job(db, run.id)
    if job:
        jobs.after_commit(job.id)
    db.expire_all()
    return _run_payload(db, db.get(AgentRun, run.id), True)  # type: ignore[arg-type]


@router.get("/ai/runs", tags=["ai"])
def ai_runs(page: Pagination = Depends(), user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    items, total = paginate(
        db, select(AgentRun).where(AgentRun.owner_id == user.id).order_by(AgentRun.created_at.desc()), page
    )
    return {
        "items": [_run_payload(db, r, False) for r in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/ai/runs/{run_id}", tags=["ai"])
def ai_run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _run_payload(db, get_owned(db, AgentRun, run_id, user.id, "AI run"), True)


@router.post("/ai/runs/{run_id}/confirm", tags=["ai"])
def ai_confirm(
    run_id: str, body: ResearchConfirm, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    run = get_owned(db, AgentRun, run_id, user.id, "AI run")
    ai.confirm_research(db, user.id, run, body.market_data_source_id, body.initial_capital)
    db.commit()
    for target in (run.backtest_run_id, (run.report or {}).get("validation_run_id")):
        job = jobs.latest_job(db, target) if target else None
        if job:
            jobs.after_commit(job.id)
    db.expire_all()
    return _run_payload(db, db.get(AgentRun, run_id), True)  # type: ignore[arg-type]


@router.post("/ai/runs/{run_id}/explain", status_code=202, tags=["ai"])
def ai_explain(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    research_run = get_owned(db, AgentRun, run_id, user.id, "AI run")
    run = ai.start_explanation(db, user.id, research_run)
    db.commit()
    job = jobs.latest_job(db, run.id)
    if job:
        jobs.after_commit(job.id)
    db.expire_all()
    return _run_payload(db, db.get(AgentRun, run.id), True)  # type: ignore[arg-type]


@router.post("/ai/runs/{run_id}/cancel", tags=["ai"])
def ai_cancel(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from app.services.runs import cancel_job_for

    get_owned(db, AgentRun, run_id, user.id, "AI run")
    job = cancel_job_for(db, user.id, run_id)
    db.commit()
    return jobs.job_payload(job) or {}


# ============================================================================ overview
@router.get("/overview", tags=["overview"])
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    def count(stmt: Any) -> int:
        return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

    recent_bt = list(
        db.scalars(
            select(BacktestRun).where(BacktestRun.owner_id == user.id).order_by(BacktestRun.created_at.desc()).limit(5)
        )
    )
    recent_disc = list(
        db.scalars(
            select(DiscoveryJob)
            .where(DiscoveryJob.owner_id == user.id)
            .order_by(DiscoveryJob.created_at.desc())
            .limit(5)
        )
    )
    last_journal = db.scalar(
        select(JournalTrade).where(JournalTrade.owner_id == user.id).order_by(JournalTrade.created_at.desc()).limit(1)
    )
    sources = list(
        db.scalars(
            select(MarketDataSource).where(
                or_(MarketDataSource.owner_id == user.id, MarketDataSource.owner_id.is_(None))
            )
        )
    )
    names = {s.id: s.name for s in db.scalars(select(Strategy).where(Strategy.owner_id == user.id))}
    from app.models import StrategyVersion

    def strategy_name(version_id: str) -> str | None:
        v = db.get(StrategyVersion, version_id)
        return names.get(v.strategy_id) if v else None

    return {
        "counts": {
            "strategies": count(select(Strategy).where(Strategy.owner_id == user.id, Strategy.status == "active")),
            "backtests": count(select(BacktestRun).where(BacktestRun.owner_id == user.id)),
            "discoveries": count(select(DiscoveryJob).where(DiscoveryJob.owner_id == user.id)),
            "active_paper_sessions": count(
                select(PaperSession).where(
                    PaperSession.owner_id == user.id, PaperSession.status.in_(("running", "paused"))
                )
            ),
            "journal_trades": count(select(JournalTrade).where(JournalTrade.owner_id == user.id)),
            "data_sources": len(sources),
        },
        "recent_backtests": [
            {
                "id": b.id,
                "status": b.status,
                "created_at": b.created_at,
                "strategy": strategy_name(b.strategy_version_id),
                "is_synthetic_data": b.is_synthetic_data,
                "net_return": (b.result_json or {}).get("metrics", {}).get("net_return"),
                "trade_count": (b.result_json or {}).get("metrics", {}).get("trade_count"),
            }
            for b in recent_bt
        ],
        "recent_discoveries": [
            {
                "id": d.id,
                "status": d.status,
                "created_at": d.created_at,
                "candidate_count": d.candidate_count,
                "job": jobs.job_payload(jobs.latest_job(db, d.id)),
            }
            for d in recent_disc
        ],
        "last_journal_activity": last_journal.created_at if last_journal else None,
        "data_status": [
            {
                "id": s.id,
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "provider": s.provider,
                "is_synthetic": s.is_synthetic,
                "rows": s.row_count,
                "first_time": s.first_time,
                "last_time": s.last_time,
                "gap_count": (s.meta or {}).get("gap_count", 0),
            }
            for s in sources
        ],
        "ai_configured": get_settings().ai_configured,
    }
