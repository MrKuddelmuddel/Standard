from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("NEXUS_ENV", "test")

from quant.data.candles import CandleSeries, build_series  # noqa: E402
from quant.strategy_schema.model import StrategyDefinition  # noqa: E402

H = 3_600_000
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H)


def make_series(
    rows: list[tuple[float, float, float, float]], timeframe: str = "1h", volume: float = 1.0
) -> CandleSeries:
    """rows: (open, high, low, close). Times are consecutive hours."""
    series, report = build_series(
        [(T0 + k * H, o, h, lo, c, volume) for k, (o, h, lo, c) in enumerate(rows)],
        "BTCUSDT",
        timeframe,
        synthetic=True,
        source="fixture",
    )
    assert report.ok, report.invalid_rows
    return series


def flat(n: int, price: float = 100.0) -> list[tuple[float, float, float, float]]:
    return [(price, price + 0.1, price - 0.1, price)] * n


def defn(**over) -> StrategyDefinition:
    """Long when close > value threshold; overrides merge into the base dict."""
    base = {
        "name": "t",
        "symbols": ["BTCUSDT"],
        "timeframe": "1h",
        "entry": {"long": {"op": "gt", "left": {"price": "close"}, "right": {"value": 1e8}}},
        "costs": {"fee_bps": 0, "slippage_bps": 0},
    }
    base.update(over)
    return StrategyDefinition.model_validate(base)


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(0)
