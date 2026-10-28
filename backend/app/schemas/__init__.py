"""Request and response schemas for the REST API (v1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------------ auth
class Credentials(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=10, max_length=200)]


class UserOut(ORM):
    id: str
    email: str
    created_at: datetime
    preferences: dict[str, Any]


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_capital: Annotated[float, Field(gt=0, le=1e9)] | None = None
    default_fee_bps: Annotated[float, Field(ge=0, le=100)] | None = None
    default_slippage_bps: Annotated[float, Field(ge=0, le=200)] | None = None
    timezone: Annotated[str, Field(max_length=60)] | None = None


# ------------------------------------------------------------------ strategies
class StrategyCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    description: Annotated[str, Field(max_length=2000)] = ""
    definition: dict[str, Any]

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be empty.")
        return v


class StrategyUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    definition: dict[str, Any] | None = None
    note: Annotated[str, Field(max_length=300)] = ""


class VersionOut(ORM):
    id: str
    strategy_id: str
    version_number: int
    schema_version: str
    definition_json: dict[str, Any]
    canonical_hash: str
    note: str
    created_at: datetime


class StrategyOut(ORM):
    id: str
    name: str
    description: str
    origin: str
    status: str
    current_version_id: str | None
    created_at: datetime
    updated_at: datetime
    current_version: VersionOut | None = None
    version_count: int = 0
    last_backtest: dict[str, Any] | None = None


class StrategyImport(BaseModel):
    document: dict[str, Any]


class ValidateRequest(BaseModel):
    definition: dict[str, Any]


# ------------------------------------------------------------------ market data
class DemoDataRequest(BaseModel):
    symbol: Literal["BTCUSDT", "ETHUSDT"] = "BTCUSDT"
    timeframe: Literal["15m", "1h", "4h", "1d"] = "1h"
    bars: Annotated[int, Field(ge=500, le=50_000)] = 8_000
    seed: int = 7


class FetchDataRequest(BaseModel):
    symbol: Literal["BTCUSDT", "ETHUSDT"] = "BTCUSDT"
    timeframe: Literal["15m", "1h", "4h", "1d"] = "1h"
    start: datetime
    end: datetime


class SourceOut(ORM):
    id: str
    provider: str
    exchange: str
    market_type: str
    symbol: str
    timeframe: str
    status: str
    is_synthetic: bool
    revision: int
    fingerprint: str | None
    row_count: int
    first_time: int | None
    last_time: int | None
    meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ backtests and validation
class BacktestCreate(BaseModel):
    strategy_version_id: str | None = None
    market_data_source_id: str
    initial_capital: Annotated[float, Field(gt=0, le=1e9)] = 10_000.0
    start_time: int | None = None
    end_time: int | None = None
    fee_bps: Annotated[float, Field(ge=0, le=100)] | None = None
    slippage_bps: Annotated[float, Field(ge=0, le=200)] | None = None


class BacktestOut(ORM):
    id: str
    strategy_version_id: str
    market_data_source_id: str
    data_revision: int
    data_fingerprint: str | None
    start_time: int | None
    end_time: int | None
    initial_capital: float
    fee_model: dict[str, Any]
    slippage_model: dict[str, Any]
    execution_model_version: str
    engine_version: str
    config_json: dict[str, Any]
    is_synthetic_data: bool
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    metrics: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    strategy: dict[str, Any] | None = None
    job: dict[str, Any] | None = None


class TradeOut(ORM):
    sequence: int
    side: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    fees: float
    slippage_cost: float
    funding_cost: float | None
    net_pnl: float
    exit_reason: str
    meta: dict[str, Any]


class ValidationCreate(BaseModel):
    strategy_version_id: str
    market_data_source_id: str
    initial_capital: Annotated[float, Field(gt=0, le=1e9)] = 10_000.0
    train_fraction: Annotated[float, Field(gt=0.2, lt=0.9)] = 0.6
    validation_fraction: Annotated[float, Field(ge=0, lt=0.5)] = 0.2
    folds: Annotated[int, Field(ge=2, le=10)] = 4
    cost_multiplier: Annotated[float, Field(ge=1, le=5)] = 2.0


class ValidationOut(ORM):
    id: str
    strategy_version_id: str
    market_data_source_id: str
    data_fingerprint: str | None
    method: str
    configuration: dict[str, Any]
    segments: list[Any] | None
    metrics: dict[str, Any] | None
    warnings: list[Any] | None
    is_synthetic_data: bool
    status: str
    error_code: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


# ------------------------------------------------------------------ discovery
class DiscoveryCreate(BaseModel):
    market_data_source_id: str
    config: dict[str, Any]


class DiscoveryOut(ORM):
    id: str
    market_data_source_id: str
    data_fingerprint: str | None
    search_config: dict[str, Any]
    status: str
    candidate_count: int
    report: dict[str, Any] | None
    is_synthetic_data: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    job: dict[str, Any] | None = None


class CandidateOut(ORM):
    id: str
    template: str
    name: str
    candidate_hash: str
    definition_json: dict[str, Any]
    status: str
    rejection_reason: str | None
    metrics: dict[str, Any]
    flags: list[Any]
    score: float | None
    score_parts: dict[str, Any]
    strategy_version_id: str | None


# ------------------------------------------------------------------ journal
Side = Literal["long", "short"]


class JournalTradeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: Annotated[str, Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9]+$")]
    market_type: Literal["spot", "futures"] = "spot"
    side: Side
    entry_time: datetime
    exit_time: datetime | None = None
    entry_price: Annotated[float, Field(gt=0)]
    exit_price: Annotated[float, Field(gt=0)] | None = None
    quantity: Annotated[float, Field(gt=0)]
    fees: Annotated[float, Field(ge=0)] = 0.0
    realized_pnl: float | None = None
    strategy_id: str | None = None
    setup: Annotated[str, Field(max_length=120)] = ""
    tags: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=20)] = []
    notes: Annotated[str, Field(max_length=5000)] = ""
    emotions: Annotated[str, Field(max_length=120)] | None = None
    rule_compliance: bool | None = None


class JournalTradeOut(ORM):
    id: str
    source_type: str
    external_id: str | None
    symbol: str
    market_type: str
    side: str
    entry_time: datetime
    exit_time: datetime | None
    entry_price: float
    exit_price: float | None
    quantity: float
    fees: float
    realized_pnl: float | None
    pnl_is_computed: bool = False
    strategy_id: str | None
    setup: str
    tags: list[Any]
    notes: str
    emotions: str | None
    rule_compliance: bool | None
    created_at: datetime


class JournalImportRequest(BaseModel):
    filename: Annotated[str, Field(max_length=200)] = "import.csv"
    content: Annotated[str, Field(max_length=5_000_000)]
    mapping: dict[str, str] | None = None
    skip_duplicates: bool = True


# ------------------------------------------------------------------ paper
class PaperCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)] = "Paper session"
    strategy_version_id: str
    market_data_source_id: str
    initial_capital: Annotated[float, Field(gt=0, le=1e9)] = 10_000.0
    start_time: int | None = None
    fee_bps: Annotated[float, Field(ge=0, le=100)] | None = None
    slippage_bps: Annotated[float, Field(ge=0, le=200)] | None = None
    auto_advance: bool = True


class PaperOut(ORM):
    id: str
    name: str
    strategy_version_id: str
    market_data_source_id: str
    data_fingerprint: str
    mode: str
    status: str
    initial_capital: float
    config_json: dict[str, Any]
    start_index: int
    end_index: int
    cursor_index: int
    equity: float
    is_synthetic_data: bool
    created_at: datetime
    updated_at: datetime
    position: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    current_time: int | None = None


class PaperAdvance(BaseModel):
    bars: Annotated[int, Field(ge=1, le=2000)] = 24


# ------------------------------------------------------------------ AI
class ResearchRequest(BaseModel):
    task: Annotated[str, Field(min_length=10, max_length=4000)]
    symbol: Literal["BTCUSDT", "ETHUSDT"] = "BTCUSDT"
    timeframe: Literal["15m", "1h", "4h", "1d"] = "1h"


class ResearchConfirm(BaseModel):
    market_data_source_id: str
    initial_capital: Annotated[float, Field(gt=0, le=1e9)] = 10_000.0
