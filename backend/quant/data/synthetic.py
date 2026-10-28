"""Deterministic synthetic candles for demos and tests. They are random, never real market data."""

from __future__ import annotations

import numpy as np

from .candles import TIMEFRAME_MS, CandleSeries, build_series

BASE_PRICE = {"BTCUSDT": 30_000.0, "ETHUSDT": 1_900.0}


def generate(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    bars: int = 5_000,
    seed: int = 7,
    start_ms: int = 1_640_995_200_000,  # 2022-01-01T00:00:00Z
) -> CandleSeries:
    """Regime-switching random walk (trend up, trend down, sideways) with clustered volatility."""
    rng = np.random.default_rng(seed)
    step = TIMEFRAME_MS[timeframe]
    scale_tf = np.sqrt(step / TIMEFRAME_MS["1h"])
    trans = np.array([[0.995, 0.002, 0.003], [0.003, 0.994, 0.003], [0.004, 0.004, 0.992]])
    drift = np.array([0.00012, -0.00012, 0.0]) * scale_tf**2
    vol = np.array([0.006, 0.008, 0.004]) * scale_tf
    regime = np.zeros(bars, dtype=int)
    h = np.zeros(bars)
    for t in range(1, bars):
        regime[t] = rng.choice(3, p=trans[regime[t - 1]])
        h[t] = 0.97 * h[t - 1] + 0.15 * rng.standard_normal()
    sigma = vol[regime] * np.exp(0.5 * h) * 0.8
    ret = np.clip(drift[regime] + sigma * rng.standard_normal(bars), -0.2, 0.2)
    close = BASE_PRICE.get(symbol, 100.0) * np.exp(np.cumsum(ret))
    open_ = np.empty(bars)
    open_[0] = close[0] / np.exp(ret[0])
    open_[1:] = close[:-1]
    wick = sigma * 0.5
    high = np.maximum(open_, close) * (1 + np.abs(rng.standard_normal(bars)) * wick)
    low = np.minimum(open_, close) * (1 - np.abs(rng.standard_normal(bars)) * wick)
    volume = rng.lognormal(6.0, 0.4, bars) * (1 + 40 * np.abs(ret))
    times = start_ms + step * np.arange(bars, dtype=np.int64)
    rows = zip(times.tolist(), open_, high, low, close, volume, strict=True)
    series, _ = build_series(rows, symbol, timeframe, synthetic=True, source=f"synthetic:seed={seed}")
    return series
