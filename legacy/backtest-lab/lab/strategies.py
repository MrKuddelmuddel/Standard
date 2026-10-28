"""Zwei einfache, erklärbare Strategien (nur Long, wie beim normalen Kauf an der Börse).

Ein Signal entsteht am Ende einer Kerze. Eingestiegen wird frühestens zur Eröffnung der nächsten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd

from .indicators import atr, ema, rsi, sma


@dataclass
class Setup:
    idx: int
    ts: pd.Timestamp
    strategy: str
    ref_price: float
    stop: float
    target: float
    note: str = ""
    side: str = "long"
    params: dict = field(default_factory=dict)


def make_setup(df: pd.DataFrame, i: int, atr_value: float, stop_atr: float, rr: float, strategy: str, note: str, params: dict) -> Setup:
    close = float(df["close"].iat[i])
    stop = close - stop_atr * atr_value
    target = close + rr * (close - stop)
    return Setup(idx=i, ts=df.index[i], strategy=strategy, ref_price=close, stop=stop, target=target, note=note, params=dict(params))


class Breakout:
    """Kurs bricht über das Hoch der letzten N Kerzen aus, im Aufwärtstrend und mit erhöhtem Volumen."""
    name = "breakout"
    base = {"lookback": 20, "atr_period": 14, "stop_atr": 1.5, "rr": 2.0, "ema_fast": 50, "ema_slow": 200, "vol_mult": 1.2}
    grid = {"lookback": [10, 20, 40], "rr": [1.5, 2.0, 3.0]}

    def __init__(self, **params):
        self.p = {**self.base, **params}

    def generate(self, df: pd.DataFrame) -> list[Setup]:
        p = self.p
        a = atr(df, p["atr_period"])
        fast, slow = ema(df["close"], p["ema_fast"]), ema(df["close"], p["ema_slow"])
        prior_high = df["high"].rolling(p["lookback"]).max().shift(1)
        vol_avg = sma(df["volume"], 20)
        cond = (df["close"] > prior_high) & (fast > slow) & (df["volume"] > p["vol_mult"] * vol_avg) & a.notna()
        return [make_setup(df, int(i), float(a.iat[i]), p["stop_atr"], p["rr"], self.name,
                           f"Ausbruch über {p['lookback']}-Kerzen-Hoch", p) for i in np.flatnonzero(cond.to_numpy())]


class Pullback:
    """Rücksetzer im Aufwärtstrend: RSI war niedrig und dreht wieder nach oben."""
    name = "pullback"
    base = {"rsi_period": 14, "rsi_entry": 35, "atr_period": 14, "stop_atr": 1.5, "rr": 1.5, "ema_fast": 50, "ema_slow": 200}
    grid = {"rsi_entry": [30, 35, 40], "rr": [1.5, 2.0, 3.0]}

    def __init__(self, **params):
        self.p = {**self.base, **params}

    def generate(self, df: pd.DataFrame) -> list[Setup]:
        p = self.p
        a = atr(df, p["atr_period"])
        r = rsi(df["close"], p["rsi_period"])
        fast, slow = ema(df["close"], p["ema_fast"]), ema(df["close"], p["ema_slow"])
        cond = (fast > slow) & (df["close"] > slow) & (r.shift(1) < p["rsi_entry"]) & (r > r.shift(1)) & a.notna()
        return [make_setup(df, int(i), float(a.iat[i]), p["stop_atr"], p["rr"], self.name,
                           f"RSI unter {p['rsi_entry']} dreht nach oben", p) for i in np.flatnonzero(cond.to_numpy())]


REGISTRY = {"breakout": Breakout, "pullback": Pullback}


def param_grid(name: str) -> list[dict]:
    grid = REGISTRY[name].grid
    keys = list(grid)
    return [dict(zip(keys, combo)) for combo in product(*(grid[k] for k in keys))]
