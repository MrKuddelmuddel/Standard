"""All ORM models. Critical history (strategy versions, backtests, fills) is never cascade-deleted."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, utcnow

JSONType = JSON


# --------------------------------------------------------------------------- users and auth
class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    __table_args__ = (CheckConstraint("status in ('active','disabled','deleted')", name="status"),)


class AuthSession(IdMixin, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(200))


class WebhookToken(IdMixin, Base):
    __tablename__ = "webhook_tokens"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    hint: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# --------------------------------------------------------------------------- strategies
class Strategy(IdMixin, TimestampMixin, Base):
    __tablename__ = "strategies"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    origin: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("strategy_versions.id", use_alter=True, name="fk_strategies_current_version"), nullable=True
    )
    __table_args__ = (
        CheckConstraint("origin in ('manual','imported','discovery','ai')", name="origin"),
        CheckConstraint("status in ('active','archived')", name="status"),
    )


class StrategyVersion(IdMixin, Base):
    __tablename__ = "strategy_versions"
    strategy_id: Mapped[str] = mapped_column(
        ForeignKey("strategies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False)
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (UniqueConstraint("strategy_id", "version_number", name="uq_strategy_versions_number"),)


@event.listens_for(StrategyVersion, "before_update")
def _versions_are_immutable(mapper, connection, target):
    raise ValueError("Strategy versions are immutable. Create a new version instead.")


# --------------------------------------------------------------------------- market data
class MarketDataSource(IdMixin, TimestampMixin, Base):
    __tablename__ = "market_data_sources"
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    exchange: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    market_type: Mapped[str] = mapped_column(String(20), default="spot", nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_time: Mapped[int | None] = mapped_column(BigInteger)
    last_time: Mapped[int | None] = mapped_column(BigInteger)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    __table_args__ = (
        UniqueConstraint("owner_id", "provider", "symbol", "timeframe", name="uq_mds_owner_provider_symbol_tf"),
    )


class Candle(Base):
    __tablename__ = "candles"
    source_id: Mapped[str] = mapped_column(ForeignKey("market_data_sources.id", ondelete="CASCADE"), primary_key=True)
    open_time: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    close_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (
        CheckConstraint("high >= low AND open > 0 AND close > 0 AND low > 0 AND volume >= 0", name="ohlcv_valid"),
    )


# --------------------------------------------------------------------------- jobs
class Job(IdMixin, Base):
    __tablename__ = "jobs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    progress_current: Mapped[int | None] = mapped_column(Integer)
    progress_total: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(500))
    locked_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status in ('queued','running','completed','failed','cancelled')", name="status"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )


# --------------------------------------------------------------------------- backtests and validation
RUN_STATUS = "status in ('queued','running','completed','failed','cancelled')"


class BacktestRun(IdMixin, Base):
    __tablename__ = "backtest_runs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    market_data_source_id: Mapped[str] = mapped_column(
        ForeignKey("market_data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    data_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    data_fingerprint: Mapped[str | None] = mapped_column(String(64))
    start_time: Mapped[int | None] = mapped_column(BigInteger)
    end_time: Mapped[int | None] = mapped_column(BigInteger)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    fee_model: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    slippage_model: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    execution_model_version: Mapped[str] = mapped_column(String(30), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    is_synthetic_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (CheckConstraint(RUN_STATUS, name="status"),)


class BacktestMetric(IdMixin, Base):
    __tablename__ = "backtest_metrics"
    backtest_run_id: Mapped[str] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (UniqueConstraint("backtest_run_id", "metric_name", name="uq_backtest_metrics_name"),)


class BacktestTrade(IdMixin, Base):
    __tablename__ = "backtest_trades"
    backtest_run_id: Mapped[str] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    entry_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    exit_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    gross_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_cost: Mapped[float] = mapped_column(Float, nullable=False)
    funding_cost: Mapped[float | None] = mapped_column(Float)
    net_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    exit_reason: Mapped[str] = mapped_column(String(30), nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("backtest_run_id", "sequence", name="uq_backtest_trades_seq"),)


class ValidationRun(IdMixin, Base):
    __tablename__ = "validation_runs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    market_data_source_id: Mapped[str] = mapped_column(
        ForeignKey("market_data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    data_fingerprint: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    segments: Mapped[list[Any] | None] = mapped_column(JSONType)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    warnings: Mapped[list[Any] | None] = mapped_column(JSONType)
    is_synthetic_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint(RUN_STATUS, name="status"),)


# --------------------------------------------------------------------------- discovery
class DiscoveryJob(IdMixin, Base):
    __tablename__ = "discovery_jobs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    market_data_source_id: Mapped[str] = mapped_column(
        ForeignKey("market_data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    data_fingerprint: Mapped[str | None] = mapped_column(String(64))
    search_config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    is_synthetic_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (CheckConstraint(RUN_STATUS, name="status"),)


class DiscoveryCandidate(IdMixin, Base):
    __tablename__ = "discovery_candidates"
    discovery_job_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id", ondelete="SET NULL"))
    template: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(300))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    flags: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    score_parts: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("discovery_job_id", "candidate_hash", name="uq_discovery_candidates_hash"),
        CheckConstraint("status in ('generated','rejected','shortlisted','validated')", name="status"),
    )


# --------------------------------------------------------------------------- journal
class JournalTrade(IdMixin, TimestampMixin, Base):
    __tablename__ = "journal_trades"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(120))
    import_id: Mapped[str | None] = mapped_column(ForeignKey("journal_imports.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market_type: Mapped[str] = mapped_column(String(20), default="spot", nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    realized_pnl: Mapped[float | None] = mapped_column(Float)
    strategy_id: Mapped[str | None] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"))
    strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id", ondelete="SET NULL"))
    setup: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    tags: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    emotions: Mapped[str | None] = mapped_column(String(120))
    rule_compliance: Mapped[bool | None] = mapped_column(Boolean)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    __table_args__ = (
        CheckConstraint("source_type in ('manual','csv','exchange_import','tradingview','paper')", name="source_type"),
        CheckConstraint("side in ('long','short')", name="side"),
        CheckConstraint("quantity > 0 AND entry_price > 0", name="positive"),
        Index("ix_journal_owner_entry", "owner_id", "entry_time"),
    )


class JournalImport(IdMixin, Base):
    __tablename__ = "journal_imports"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_imported: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False)
    errors: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# --------------------------------------------------------------------------- paper trading
class PaperSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "paper_sessions"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    market_data_source_id: Mapped[str] = mapped_column(
        ForeignKey("market_data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    data_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), default="historical_replay", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    start_index: Mapped[int] = mapped_column(Integer, nullable=False)
    end_index: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor_index: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    equity_curve: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    is_synthetic_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (
        CheckConstraint("status in ('created','running','paused','stopped','completed')", name="status"),
        CheckConstraint("mode in ('historical_replay')", name="mode"),
    )


class PaperOrder(IdMixin, Base):
    __tablename__ = "paper_orders"
    session_id: Mapped[str] = mapped_column(
        ForeignKey("paper_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    bar_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    intent: Mapped[str] = mapped_column(String(20), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key", name="uq_paper_orders_key"),)


class PaperFill(IdMixin, Base):
    __tablename__ = "paper_fills"
    session_id: Mapped[str] = mapped_column(
        ForeignKey("paper_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_id: Mapped[str] = mapped_column(ForeignKey("paper_orders.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    bar_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    ref_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key", name="uq_paper_fills_key"),)


class PaperPosition(IdMixin, Base):
    __tablename__ = "paper_positions"
    session_id: Mapped[str] = mapped_column(
        ForeignKey("paper_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    side: Mapped[str | None] = mapped_column(String(5))
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float)
    stop: Mapped[float | None] = mapped_column(Float)
    target: Mapped[float | None] = mapped_column(Float)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# --------------------------------------------------------------------------- tradingview
class TradingViewAlert(IdMixin, Base):
    __tablename__ = "tradingview_alerts"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    price: Mapped[float | None] = mapped_column(Float)
    alert_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="stored", nullable=False)
    journal_trade_id: Mapped[str | None] = mapped_column(ForeignKey("journal_trades.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("owner_id", "event_id", name="uq_tv_alerts_event"),)


# --------------------------------------------------------------------------- AI agent
class AgentRun(IdMixin, Base):
    __tablename__ = "agent_runs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="research", nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    structured_output: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"))
    backtest_run_id: Mapped[str | None] = mapped_column(ForeignKey("backtest_runs.id", ondelete="SET NULL"))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentToolCall(IdMixin, Base):
    __tablename__ = "agent_tool_calls"
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(60), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# --------------------------------------------------------------------------- audit
class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
