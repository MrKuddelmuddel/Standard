"""Strategy schema v1.0: a restricted, versioned JSON expression tree. No code execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA_VERSION = "1.0"
SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SUPPORTED_TIMEFRAMES = ("15m", "1h", "4h", "1d")
SUPPORTED_INDICATORS = {
    "ema": "Exponential moving average of the source price.",
    "sma": "Simple moving average of the source price.",
    "rsi": "Relative Strength Index (Wilder) of the close.",
    "atr": "Average True Range (Wilder).",
    "highest": "Highest high of the previous N candles, excluding the current candle.",
    "lowest": "Lowest low of the previous N candles, excluding the current candle.",
    "volume_sma": "Simple moving average of volume.",
}
MAX_INDICATORS = 12
MAX_DEPTH = 5
MAX_NODES = 40

Symbol = Literal["BTCUSDT", "ETHUSDT"]
Timeframe = Literal["15m", "1h", "4h", "1d"]
PriceField = Literal["open", "high", "low", "close", "volume"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Indicator(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
    type: Literal["ema", "sma", "rsi", "atr", "highest", "lowest", "volume_sma"]
    period: Annotated[int, Field(ge=2, le=500)]
    source: PriceField = "close"


class IndicatorRef(_Strict):
    ind: str


class PriceRef(_Strict):
    price: PriceField


class ValueRef(_Strict):
    value: Annotated[float, Field(ge=-1e9, le=1e9)]


Operand = IndicatorRef | PriceRef | ValueRef


class Compare(_Strict):
    op: Literal["gt", "lt", "gte", "lte", "crosses_above", "crosses_below"]
    left: Operand
    right: Operand


class AllOf(_Strict):
    all: Annotated[list[Condition], Field(min_length=1, max_length=8)]


class AnyOf(_Strict):
    any: Annotated[list[Condition], Field(min_length=1, max_length=8)]


class NotOf(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    not_: Condition = Field(alias="not")


Condition = Compare | AllOf | AnyOf | NotOf
AllOf.model_rebuild()
AnyOf.model_rebuild()
NotOf.model_rebuild()


class SideConditions(_Strict):
    long: Condition | None = None
    short: Condition | None = None


class StopRule(_Strict):
    type: Literal["none", "percent", "atr"] = "none"
    value: Annotated[float, Field(ge=0, le=50)] = 0
    atr_indicator: str | None = None


class TakeProfitRule(_Strict):
    type: Literal["none", "percent", "atr", "r_multiple"] = "none"
    value: Annotated[float, Field(ge=0, le=100)] = 0
    atr_indicator: str | None = None


class RiskManagement(_Strict):
    stop_loss: StopRule = StopRule()
    take_profit: TakeProfitRule = TakeProfitRule()
    max_bars_in_trade: Annotated[int, Field(ge=1, le=5000)] | None = None


class PositionSizing(_Strict):
    type: Literal["fixed_fraction", "risk_percent"] = "fixed_fraction"
    fraction: Annotated[float, Field(gt=0, le=1)] = 1.0
    risk_percent: Annotated[float, Field(gt=0, le=10)] | None = None


class Execution(_Strict):
    fill_model: Literal["next_open"] = "next_open"


class Costs(_Strict):
    fee_bps: Annotated[float, Field(ge=0, le=100)] = 10.0
    slippage_bps: Annotated[float, Field(ge=0, le=200)] = 5.0


class StrategyDefinition(_Strict):
    schema_version: Literal["1.0"] = "1.0"
    name: Annotated[str, Field(min_length=1, max_length=80)]
    description: Annotated[str, Field(max_length=2000)] = ""
    symbols: Annotated[list[Symbol], Field(min_length=1, max_length=2)]
    timeframe: Timeframe
    market_type: Literal["spot", "futures_sim"] = "spot"
    direction: Literal["long", "short", "long_short"] = "long"
    indicators: Annotated[list[Indicator], Field(max_length=MAX_INDICATORS)] = []
    entry: SideConditions
    exit: SideConditions = SideConditions()
    risk_management: RiskManagement = RiskManagement()
    position_sizing: PositionSizing = PositionSizing()
    execution: Execution = Execution()
    costs: Costs = Costs()

    @model_validator(mode="after")
    def _check(self) -> StrategyDefinition:
        errors: list[str] = []
        ids = [i.id for i in self.indicators]
        dupes = sorted({x for x in ids if ids.count(x) > 1})
        if dupes:
            errors.append(f"Indicator ids must be unique: {', '.join(dupes)}.")
        known = {i.id: i for i in self.indicators}
        if len(set(self.symbols)) != len(self.symbols):
            errors.append("Symbols must not repeat.")
        if self.direction in ("short", "long_short") and self.market_type != "futures_sim":
            errors.append("Short positions require market_type 'futures_sim'. Spot cannot be shorted.")
        wants_long = self.direction in ("long", "long_short")
        wants_short = self.direction in ("short", "long_short")
        if wants_long and self.entry.long is None:
            errors.append("direction includes long, so entry.long is required.")
        if wants_short and self.entry.short is None:
            errors.append("direction includes short, so entry.short is required.")
        if not wants_long and (self.entry.long or self.exit.long):
            errors.append("Long conditions are set but direction does not include long.")
        if not wants_short and (self.entry.short or self.exit.short):
            errors.append("Short conditions are set but direction does not include short.")
        nodes = 0
        for label, cond in (
            ("entry.long", self.entry.long),
            ("entry.short", self.entry.short),
            ("exit.long", self.exit.long),
            ("exit.short", self.exit.short),
        ):
            if cond is None:
                continue
            depth, count, refs = _walk(cond)
            nodes += count
            if depth > MAX_DEPTH:
                errors.append(f"{label} is nested too deeply ({depth} > {MAX_DEPTH}).")
            for r in sorted(refs - known.keys()):
                errors.append(f"{label} references unknown indicator '{r}'.")
        if nodes > MAX_NODES:
            errors.append(f"Too many condition nodes ({nodes} > {MAX_NODES}).")
        sl, tp = self.risk_management.stop_loss, self.risk_management.take_profit
        for label, rule in (("stop_loss", sl), ("take_profit", tp)):
            if rule.type == "none":
                continue
            if rule.value <= 0:
                errors.append(f"{label}.value must be greater than 0.")
            if rule.type == "atr":
                ind = known.get(rule.atr_indicator or "")
                if ind is None or ind.type != "atr":
                    errors.append(f"{label} of type 'atr' needs atr_indicator pointing to an 'atr' indicator.")
            if rule.type == "percent" and rule.value >= (50 if label == "stop_loss" else 100):
                errors.append(f"{label}.value is out of range.")
        if tp.type == "r_multiple" and sl.type == "none":
            errors.append("take_profit 'r_multiple' requires a stop_loss.")
        ps = self.position_sizing
        if ps.type == "risk_percent":
            if ps.risk_percent is None:
                errors.append("position_sizing 'risk_percent' requires risk_percent.")
            if sl.type == "none":
                errors.append("position_sizing 'risk_percent' requires a stop_loss.")
        if errors:
            raise ValueError(" | ".join(errors))
        return self

    def warmup_bars(self) -> int:
        """Bars needed before every indicator has a value (plus one for crossover checks)."""
        need = 1
        for ind in self.indicators:
            need = max(need, ind.period + 1)
        return need


def _walk(cond: Condition, depth: int = 1) -> tuple[int, int, set[str]]:
    if isinstance(cond, Compare):
        refs = {o.ind for o in (cond.left, cond.right) if isinstance(o, IndicatorRef)}
        return depth, 1, refs
    children = cond.all if isinstance(cond, AllOf) else cond.any if isinstance(cond, AnyOf) else [cond.not_]
    max_d, count, refs = depth, 1, set()
    for child in children:
        d, c, r = _walk(child, depth + 1)
        max_d, count, refs = max(max_d, d), count + c, refs | r
    return max_d, count, refs


@dataclass
class ValidationIssue:
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


def validate_definition(data: Any) -> tuple[StrategyDefinition | None, list[ValidationIssue]]:
    """Validate raw JSON. Returns the parsed definition or human-readable issues."""
    if not isinstance(data, dict):
        return None, [ValidationIssue("", "Strategy definition must be a JSON object.")]
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        return None, [
            ValidationIssue("schema_version", f"Unsupported schema_version '{version}'. Supported: {SCHEMA_VERSION}.")
        ]
    try:
        return StrategyDefinition.model_validate(data), []
    except ValidationError as exc:
        issues: list[ValidationIssue] = []
        seen: set[tuple[str, str]] = set()
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if not str(p).startswith(("function-", "tagged-union"))]
            loc = [
                p
                for p in loc
                if p not in ("Compare", "AllOf", "AnyOf", "NotOf", "IndicatorRef", "PriceRef", "ValueRef")
            ]
            path = ".".join(loc)
            msg = str(err["msg"]).removeprefix("Value error, ")
            for part in msg.split(" | "):
                key = (path, part)
                if key not in seen:
                    seen.add(key)
                    issues.append(ValidationIssue(path, part))
        return None, issues


def canonical_json(defn: StrategyDefinition) -> str:
    return json.dumps(
        defn.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def canonical_hash(defn: StrategyDefinition) -> str:
    return hashlib.sha256(canonical_json(defn).encode("utf-8")).hexdigest()
