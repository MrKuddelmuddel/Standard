"""Paper trading as historical replay. Uses the same Simulator as the backtest engine.

Each advance processes the next candles of the stored dataset, persists simulator state, orders and fills in one
transaction. Orders and fills carry unique idempotency keys (`<bar_time>:<intent>`), so reprocessing a bar after a
crash cannot create duplicates. No real orders are ever sent; there is no live mode.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import MarketDataSource, PaperFill, PaperOrder, PaperPosition, PaperSession, StrategyVersion
from app.services.audit import audit
from app.services.market_data import get_source, load_series
from app.services.runs import _check_compat, owned_version
from quant.engine import resolve_window
from quant.engine.signals import build_signals
from quant.engine.simulator import SimState, Simulator
from quant.strategy_schema import StrategyDefinition

TRANSITIONS = {
    "start": ({"created", "paused"}, "running"),
    "pause": ({"running"}, "paused"),
    "resume": ({"paused"}, "running"),
    "stop": ({"created", "running", "paused"}, "stopped"),
}


def create_session(db: Session, owner_id: str, body: Any) -> PaperSession:
    version, _ = owned_version(db, body.strategy_version_id, owner_id)
    src = get_source(db, body.market_data_source_id, owner_id)
    defn = StrategyDefinition.model_validate(version.definition_json)
    _check_compat(defn, src)
    series = load_series(db, src)
    start_from = int(np.searchsorted(series.open_time, body.start_time)) if body.start_time else None
    start, end = resolve_window(series, defn, start_from, None)
    fee = defn.costs.fee_bps if body.fee_bps is None else body.fee_bps
    slip = defn.costs.slippage_bps if body.slippage_bps is None else body.slippage_bps
    sess = PaperSession(
        owner_id=owner_id,
        name=body.name,
        strategy_version_id=version.id,
        market_data_source_id=src.id,
        data_fingerprint=src.fingerprint or "",
        initial_capital=body.initial_capital,
        config_json={
            "fee_bps": fee,
            "slippage_bps": slip,
            "auto_advance": body.auto_advance,
            "execution_model": "next_open_v1",
            "mode_note": "Historical replay of stored candles. Simulation only.",
        },
        start_index=start,
        end_index=end,
        cursor_index=start,
        state_json=SimState(realized=body.initial_capital).to_dict(),
        equity=body.initial_capital,
        equity_curve=[],
        is_synthetic_data=src.is_synthetic,
    )
    db.add(sess)
    db.flush()
    db.add(PaperPosition(session_id=sess.id))
    audit(db, owner_id, "paper.created", "paper_session", sess.id, {"version": version.id, "source": src.id})
    return sess


def transition(db: Session, sess: PaperSession, action: str, owner_id: str) -> PaperSession:
    allowed, target = TRANSITIONS[action]
    if sess.status not in allowed:
        raise ApiError(409, "invalid_transition", f"Cannot {action} a session that is {sess.status}.")
    sess.status = target
    audit(db, owner_id, f"paper.{action}", "paper_session", sess.id)
    return sess


def _lock(db: Session, session_id: str) -> PaperSession:
    stmt = select(PaperSession).where(PaperSession.id == session_id)
    if not get_settings().is_sqlite:
        stmt = stmt.with_for_update()
    sess = db.scalar(stmt)
    assert sess is not None
    return sess


def advance(db: Session, session_id: str, bars: int) -> dict[str, Any]:
    """Process up to `bars` candles. Safe to call repeatedly and concurrently (row lock + unique keys)."""
    sess = _lock(db, session_id)
    if sess.status != "running":
        raise ApiError(409, "not_running", f"Session is {sess.status}. Start or resume it first.")
    bars = min(bars, get_settings().paper_max_bars_per_step)
    src = db.get(MarketDataSource, sess.market_data_source_id)
    version = db.get(StrategyVersion, sess.strategy_version_id)
    assert src is not None and version is not None
    series = load_series(db, src)
    if series.fingerprint() != sess.data_fingerprint:
        sess.status = "stopped"
        audit(db, sess.owner_id, "paper.stopped_data_changed", "paper_session", sess.id)
        raise ApiError(
            409, "data_changed", "The data source changed. The session was stopped to keep results consistent."
        )
    defn = StrategyDefinition.model_validate(version.definition_json)
    signals = build_signals(series, defn)
    sim = Simulator(
        series,
        defn,
        signals,
        sess.initial_capital,
        sess.end_index,
        sess.config_json["fee_bps"],
        sess.config_json["slippage_bps"],
        SimState.from_dict(sess.state_json),
    )
    new_orders = new_fills = 0
    processed = 0
    curve = list(sess.equity_curve)
    while processed < bars and sess.cursor_index < sess.end_index:
        i = sess.cursor_index
        out = sim.process_bar(i)
        orders: dict[str, PaperOrder] = {}
        for ev in out.events:
            if ev["type"] == "order":
                exists = db.scalar(
                    select(PaperOrder).where(PaperOrder.session_id == sess.id, PaperOrder.idempotency_key == ev["key"])
                )
                if exists is None:
                    exists = PaperOrder(
                        session_id=sess.id,
                        idempotency_key=ev["key"],
                        bar_time=ev["time"],
                        side=ev["side"],
                        intent=ev["intent"],
                        order_type=ev["order_type"],
                        quantity=ev["qty"],
                        status="filled",
                        reason=ev.get("reason"),
                    )
                    db.add(exists)
                    db.flush()
                    new_orders += 1
                orders[ev["key"]] = exists
            elif ev["type"] == "order_rejected":
                if (
                    db.scalar(
                        select(PaperOrder.id).where(
                            PaperOrder.session_id == sess.id, PaperOrder.idempotency_key == ev["key"]
                        )
                    )
                    is None
                ):
                    db.add(
                        PaperOrder(
                            session_id=sess.id,
                            idempotency_key=ev["key"],
                            bar_time=ev["time"],
                            side="buy" if ev["side"] == "long" else "sell",
                            intent=f"open_{ev['side']}",
                            order_type="market",
                            quantity=0.0,
                            status="rejected",
                            reason=ev["reason"][:60],
                        )
                    )
                    new_orders += 1
            elif ev["type"] == "fill":
                if (
                    db.scalar(
                        select(PaperFill.id).where(
                            PaperFill.session_id == sess.id, PaperFill.idempotency_key == ev["key"]
                        )
                    )
                    is None
                ):
                    db.add(
                        PaperFill(
                            session_id=sess.id,
                            order_id=orders[ev["key"]].id,
                            idempotency_key=ev["key"],
                            bar_time=ev["time"],
                            price=ev["price"],
                            ref_price=ev["ref_price"],
                            quantity=ev["qty"],
                            fee=ev["fee"],
                        )
                    )
                    new_fills += 1
        sess.cursor_index = i + 1
        sess.equity = out.equity
        curve.append([int(series.open_time[i]), round(out.equity, 4)])
        processed += 1
    sess.state_json = sim.state.to_dict()
    sess.equity_curve = curve[-2000:]
    pos = db.scalar(select(PaperPosition).where(PaperPosition.session_id == sess.id))
    p = sim.state.position
    if pos is not None:
        last_close = float(series.close[sess.cursor_index - 1]) if sess.cursor_index > 0 else 0.0
        pos.side = p["side"] if p else None
        pos.quantity = p["qty"] if p else 0.0
        pos.entry_price = p["entry_fill"] if p else None
        pos.stop, pos.target = (p.get("stop"), p.get("target")) if p else (None, None)
        pos.unrealized_pnl = (
            ((1 if p["side"] == "long" else -1) * p["qty"] * (last_close - p["entry_fill"])) if p else 0.0
        )
    if sess.cursor_index >= sess.end_index:
        sess.status = "completed"
        audit(db, sess.owner_id, "paper.completed", "paper_session", sess.id)
    return {"processed": processed, "new_orders": new_orders, "new_fills": new_fills, "status": sess.status}


def auto_tick() -> None:
    """Called by the worker: advance running sessions that opted into auto-advance by a few bars."""
    from app.db.session import session_scope

    with session_scope() as db:
        ids = list(db.scalars(select(PaperSession.id).where(PaperSession.status == "running")))
    for sid in ids:
        try:
            with session_scope() as db:
                sess = db.get(PaperSession, sid)
                if sess is None or not sess.config_json.get("auto_advance"):
                    continue
                advance(db, sid, get_settings().paper_auto_bars_per_tick)
        except ApiError:
            continue


def session_payload(db: Session, sess: PaperSession) -> dict[str, Any]:
    pos = db.scalar(select(PaperPosition).where(PaperPosition.session_id == sess.id))
    total = sess.end_index - sess.start_index
    current_time = sess.equity_curve[-1][0] if sess.equity_curve else None
    data = {
        c.name: getattr(sess, c.name)
        for c in PaperSession.__table__.columns
        if c.name not in ("state_json", "equity_curve", "owner_id")
    }
    return {
        **data,
        "current_time": current_time,
        "position": None
        if pos is None or pos.side is None
        else {
            "side": pos.side,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "stop": pos.stop,
            "target": pos.target,
            "unrealized_pnl": pos.unrealized_pnl,
        },
        "progress": {"processed": sess.cursor_index - sess.start_index, "total": total},
    }
