"""Daten laden, prüfen und (für Tests) künstlich erzeugen.

Echte Kurse holt fetch_data.py auf deinem eigenen Rechner. Die künstlichen Daten hier sind
reine Zufallsdaten. Sie taugen nur, um die Technik zu testen, nie um eine Strategie zu bewerten.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume"]


def load_csv(path: str) -> pd.DataFrame:
    """CSV mit Spalten timestamp (ms, s oder Text), open, high, low, close, volume."""
    raw = pd.read_csv(path)
    ts_col = "timestamp" if "timestamp" in raw.columns else raw.columns[0]
    ts = raw[ts_col]
    if np.issubdtype(ts.dtype, np.number):
        unit = "ms" if float(ts.iloc[0]) > 1e11 else "s"
        index = pd.to_datetime(ts, unit=unit, utc=True)
    else:
        index = pd.to_datetime(ts, utc=True)
    df = raw[COLUMNS].astype(float).copy()
    df.index = pd.DatetimeIndex(index, name="timestamp")
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df.attrs["synthetic"] = False
    return df


def check_quality(df: pd.DataFrame, step_minutes: int = 60) -> list[str]:
    """Gibt eine Liste von Auffälligkeiten zurück. Leer heißt: nichts gefunden."""
    issues: list[str] = []
    if df.isna().any().any():
        issues.append("Es gibt leere Werte (NaN).")
    bad = (df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1))
    if bad.any():
        issues.append(f"{int(bad.sum())} Kerzen mit unmöglichen Hoch/Tief-Werten.")
    gaps = df.index.to_series().diff().dropna()
    big = gaps[gaps > pd.Timedelta(minutes=step_minutes * 1.5)]
    if len(big):
        issues.append(f"{len(big)} Lücken in den Zeitstempeln, größte: {big.max()}.")
    zero = int((df["volume"] <= 0).sum())
    if zero:
        issues.append(f"{zero} Kerzen ohne Handelsvolumen.")
    return issues


def synthetic(n: int = 20000, seed: int = 7, step_minutes: int = 60, start: str = "2022-01-01") -> pd.DataFrame:
    """Künstliche Kerzen mit Trendphasen, Seitwärtsphasen und schwankender Unruhe (Zufall)."""
    rng = np.random.default_rng(seed)
    trans = np.array([[0.995, 0.002, 0.003], [0.003, 0.994, 0.003], [0.004, 0.004, 0.992]])
    drift = np.array([0.00012, -0.00012, 0.0])
    vol = np.array([0.006, 0.008, 0.004])
    reg = np.zeros(n, dtype=int)
    for t in range(1, n):
        reg[t] = rng.choice(3, p=trans[reg[t - 1]])
    h = np.zeros(n)
    for t in range(1, n):
        h[t] = 0.97 * h[t - 1] + 0.15 * rng.standard_normal()
    scale = vol[reg] * np.exp(0.5 * h) * 0.8
    ret = np.clip(drift[reg] + scale * rng.standard_normal(n), -0.15, 0.15)
    close = 30000.0 * np.exp(np.cumsum(ret))
    open_ = np.empty(n)
    open_[0] = close[0] / np.exp(ret[0])
    open_[1:] = close[:-1]
    wick = scale * 0.5
    high = np.maximum(open_, close) * (1 + np.abs(rng.standard_normal(n)) * wick)
    low = np.minimum(open_, close) * (1 - np.abs(rng.standard_normal(n)) * wick)
    volume = rng.lognormal(6.0, 0.4, n) * (1 + 40 * np.abs(ret))
    index = pd.date_range(start, periods=n, freq=f"{step_minutes}min", tz="UTC", name="timestamp")
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index)
    df.attrs["synthetic"] = True
    return df


def fetch_ohlcv_all(exchange, symbol: str, timeframe: str, since_ms: int, until_ms: int | None = None,
                    limit: int = 1000, pause: float | None = None) -> list[list[float]]:
    """Holt Kerzen seitenweise von einer ccxt-Börse. Öffentliche Daten, kein Schlüssel nötig.

    `exchange` ist ein ccxt-Objekt. Für Tests kann ein Ersatzobjekt mit fetch_ohlcv() übergeben werden.
    """
    rows: list[list[float]] = []
    cursor = since_ms
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=limit)
        if not batch:
            break
        rows.extend(batch)
        last = batch[-1][0]
        if until_ms is not None and last >= until_ms:
            break
        if len(batch) < limit or last <= cursor:
            break
        cursor = last + 1
        time.sleep(pause if pause is not None else getattr(exchange, "rateLimit", 200) / 1000.0)
    if until_ms is not None:
        rows = [r for r in rows if r[0] <= until_ms]
    seen: set[int] = set()
    unique = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            unique.append(r)
    return unique
