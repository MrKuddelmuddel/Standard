"""Causal indicators: the value at index i only uses data up to and including i. Warm-up values are NaN."""

from __future__ import annotations

import numpy as np

from ..data.candles import CandleSeries


def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    c = np.cumsum(np.insert(x.astype(float), 0, 0.0))
    out[n - 1 :] = (c[n:] - c[:-n]) / n
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """EMA seeded with the SMA of the first n values (alpha = 2 / (n + 1))."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    alpha = 2.0 / (n + 1)
    prev = float(np.mean(x[:n]))
    out[n - 1] = prev
    for i in range(n, len(x)):
        prev = alpha * float(x[i]) + (1 - alpha) * prev
        out[i] = prev
    return out


def _wilder(values: np.ndarray, n: int, first: int) -> np.ndarray:
    """Wilder smoothing: seed = mean(values[first-n+1 .. first]), then prev + (v - prev) / n."""
    out = np.full(len(values), np.nan)
    if len(values) <= first:
        return out
    prev = float(np.mean(values[first - n + 1 : first + 1]))
    out[first] = prev
    for i in range(first + 1, len(values)):
        prev = prev + (float(values[i]) - prev) / n
        out[i] = prev
    return out


def rsi(close: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(close), np.nan)
    if len(close) <= n:
        return out
    d = np.diff(close, prepend=close[0])
    up = np.clip(d, 0, None)
    down = np.clip(-d, 0, None)
    au = _wilder(up, n, n)
    ad = _wilder(down, n, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = au / ad
        val = 100 - 100 / (1 + rs)
    val = np.where((ad == 0) & (au > 0), 100.0, val)
    val = np.where((ad == 0) & (au == 0), 50.0, val)
    out[n:] = val[n:]
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr[0] = high[0] - low[0]
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    return _wilder(true_range(high, low, close), n, n - 1)


def highest_prev(high: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(high), np.nan)
    for i in range(n, len(high)):
        out[i] = float(np.max(high[i - n : i]))
    return out


def lowest_prev(low: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(low), np.nan)
    for i in range(n, len(low)):
        out[i] = float(np.min(low[i - n : i]))
    return out


def compute(series: CandleSeries, ind_type: str, period: int, source: str = "close") -> np.ndarray:
    src = getattr(series, source)
    if ind_type == "ema":
        return ema(src, period)
    if ind_type == "sma":
        return sma(src, period)
    if ind_type == "rsi":
        return rsi(series.close, period)
    if ind_type == "atr":
        return atr(series.high, series.low, series.close, period)
    if ind_type == "highest":
        return highest_prev(series.high, period)
    if ind_type == "lowest":
        return lowest_prev(series.low, period)
    if ind_type == "volume_sma":
        return sma(series.volume, period)
    raise ValueError(f"Unknown indicator type '{ind_type}'.")
