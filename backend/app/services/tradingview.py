"""TradingView alert webhook. Alerts are stored and can be linked to the journal. They never trigger real orders.

TradingView cannot send custom headers, so the shared secret is a field in the JSON body. The secret is stored only
as a SHA-256 hash. Replay protection: event_id is unique per user and the alert time must be close to server time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import new_token, token_hash
from app.models import JournalTrade, TradingViewAlert, WebhookToken
from app.schemas import JournalTradeIn
from app.services.audit import audit
from app.services.journal import create_trade
from quant.data.csv_import import parse_timestamp

EXAMPLE_PAYLOAD = {
    "secret": "<your webhook secret>",
    "event_id": "{{strategy.order.id}}-{{timenow}}",
    "symbol": "BTCUSDT",
    "action": "buy",
    "price": "{{close}}",
    "time": "{{timenow}}",
    "strategy": "EMA cross",
    "note": "optional text",
}


class AlertPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    secret: Annotated[str, Field(min_length=16, max_length=200)]
    event_id: Annotated[str, Field(min_length=1, max_length=100)]
    symbol: Annotated[str, Field(min_length=2, max_length=20)]
    action: Literal["buy", "sell", "long", "short", "close"]
    price: Annotated[float, Field(gt=0)] | None = None
    time: str
    strategy: Annotated[str, Field(max_length=120)] = ""
    note: Annotated[str, Field(max_length=500)] = ""

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        v = v.upper().replace("BINANCE:", "").replace("/", "").replace(".P", "")
        if not v.isalnum():
            raise ValueError("Symbol must be alphanumeric.")
        return v


def create_token(db: Session, owner_id: str) -> str:
    for t in db.scalars(select(WebhookToken).where(WebhookToken.owner_id == owner_id, WebhookToken.revoked.is_(False))):
        t.revoked = True
    token = new_token(24)
    db.add(WebhookToken(owner_id=owner_id, token_hash=token_hash(token), hint=token[-4:]))
    audit(db, owner_id, "tradingview.token_rotated", "webhook_token")
    return token


def receive(db: Session, raw: dict[str, Any]) -> TradingViewAlert:
    try:
        payload = AlertPayload.model_validate(raw)
    except ValueError as exc:
        raise ApiError(422, "invalid_payload", "Alert payload is invalid.") from exc
    tok = db.scalar(
        select(WebhookToken).where(
            WebhookToken.token_hash == token_hash(payload.secret), WebhookToken.revoked.is_(False)
        )
    )
    if tok is None:
        raise ApiError(401, "invalid_secret", "Unknown or revoked webhook secret.")
    try:
        alert_time = datetime.fromtimestamp(parse_timestamp(payload.time) / 1000, tz=UTC)
    except ValueError as exc:
        raise ApiError(422, "invalid_payload", "Field 'time' must be ISO 8601 or a Unix timestamp.") from exc
    skew = abs((datetime.now(UTC) - alert_time).total_seconds())
    if skew > get_settings().webhook_max_clock_skew_seconds:
        raise ApiError(422, "stale_alert", "Alert time is too far from server time (possible replay).")
    alert = TradingViewAlert(
        owner_id=tok.owner_id,
        event_id=payload.event_id,
        symbol=payload.symbol,
        action=payload.action,
        price=payload.price,
        alert_time=alert_time,
        payload=payload.model_dump(exclude={"secret"}),
    )
    db.add(alert)
    tok.last_used_at = datetime.now(UTC)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "duplicate_event", "This event_id was already received.") from exc
    audit(
        db,
        tok.owner_id,
        "tradingview.alert_received",
        "tradingview_alert",
        alert.id,
        {"symbol": alert.symbol, "action": alert.action},
    )
    return alert


def link_to_journal(db: Session, owner_id: str, alert: TradingViewAlert, quantity: float) -> JournalTrade:
    if alert.journal_trade_id:
        raise ApiError(409, "already_linked", "Alert is already linked to a journal trade.")
    if alert.action == "close" or alert.price is None:
        raise ApiError(422, "not_linkable", "Only entry alerts with a price can open a journal trade.")
    side = "long" if alert.action in ("buy", "long") else "short"
    data = JournalTradeIn(
        symbol=alert.symbol,
        side=side,
        entry_time=alert.alert_time,
        entry_price=alert.price,
        quantity=quantity,
        setup=str(alert.payload.get("strategy", ""))[:120],
        notes=str(alert.payload.get("note", ""))[:5000],
        tags=["tradingview"],
    )
    trade, _ = create_trade(db, owner_id, data, "tradingview", external_id=alert.event_id)
    db.flush()
    alert.journal_trade_id, alert.status = trade.id, "linked"
    return trade
