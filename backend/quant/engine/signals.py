"""Evaluate the condition tree into boolean arrays. Every operator uses only bars i and i-1 (causal)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import indicators as ind
from ..data.candles import CandleSeries
from ..strategy_schema.model import (
    AllOf,
    AnyOf,
    Compare,
    Condition,
    IndicatorRef,
    NotOf,
    Operand,
    PriceRef,
    StrategyDefinition,
    ValueRef,
)


@dataclass
class SignalSet:
    indicators: dict[str, np.ndarray]
    entry_long: np.ndarray
    entry_short: np.ndarray
    exit_long: np.ndarray
    exit_short: np.ndarray


def compute_indicators(series: CandleSeries, defn: StrategyDefinition) -> dict[str, np.ndarray]:
    return {i.id: ind.compute(series, i.type, i.period, i.source) for i in defn.indicators}


def _operand(op: Operand, series: CandleSeries, values: dict[str, np.ndarray]) -> np.ndarray:
    if isinstance(op, IndicatorRef):
        return values[op.ind]
    if isinstance(op, PriceRef):
        return np.asarray(getattr(series, op.price), dtype=float)
    assert isinstance(op, ValueRef)
    return np.full(len(series), float(op.value))


def evaluate(cond: Condition, series: CandleSeries, values: dict[str, np.ndarray]) -> np.ndarray:
    n = len(series)
    if isinstance(cond, Compare):
        a = _operand(cond.left, series, values)
        b = _operand(cond.right, series, values)
        valid = ~(np.isnan(a) | np.isnan(b))
        with np.errstate(invalid="ignore"):
            if cond.op == "gt":
                return valid & (a > b)
            if cond.op == "lt":
                return valid & (a < b)
            if cond.op == "gte":
                return valid & (a >= b)
            if cond.op == "lte":
                return valid & (a <= b)
            prev_valid = np.zeros(n, dtype=bool)
            prev_valid[1:] = valid[1:] & valid[:-1]
            out = np.zeros(n, dtype=bool)
            if cond.op == "crosses_above":
                out[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
            else:
                out[1:] = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
            return prev_valid & out
    if isinstance(cond, AllOf):
        res = np.ones(n, dtype=bool)
        for c in cond.all:
            res &= evaluate(c, series, values)
        return res
    if isinstance(cond, AnyOf):
        res = np.zeros(n, dtype=bool)
        for c in cond.any:
            res |= evaluate(c, series, values)
        return res
    assert isinstance(cond, NotOf)
    return ~evaluate(cond.not_, series, values)


def build_signals(series: CandleSeries, defn: StrategyDefinition) -> SignalSet:
    values = compute_indicators(series, defn)
    n = len(series)
    empty = np.zeros(n, dtype=bool)

    def ev(c: Condition | None) -> np.ndarray:
        return evaluate(c, series, values) if c is not None else empty.copy()

    return SignalSet(values, ev(defn.entry.long), ev(defn.entry.short), ev(defn.exit.long), ev(defn.exit.short))
