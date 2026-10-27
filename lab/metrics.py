"""Kennzahlen und ein ehrlicher Maßstab, ob ein Ergebnis mehr als Zufall sein könnte."""
from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float(np.min((equity - peak) / peak))


def summarize(trades: list[dict], equity: np.ndarray, start_capital: float) -> dict:
    rs = np.array([t["r"] for t in trades], dtype=float)
    pnl = np.array([t["pnl"] for t in trades], dtype=float)
    n = len(rs)
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return {
        "trades": n,
        "win_rate": float((rs > 0).mean()) if n else float("nan"),
        "avg_r": float(rs.mean()) if n else float("nan"),
        "profit_factor": float(wins / losses) if losses > 0 else (float("inf") if wins > 0 else float("nan")),
        "return_pct": float(equity[-1] / start_capital - 1) if len(equity) else 0.0,
        "max_dd": max_drawdown(equity),
        "fees": float(sum(t["fees"] for t in trades)),
    }


def bootstrap_ci(rs: list[float], runs: int = 2000, seed: int = 1) -> tuple[float, float]:
    """95-%-Spanne für den Durchschnitt in R, wenn man die Trades zufällig neu zieht."""
    arr = np.asarray(rs, dtype=float)
    if len(arr) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(runs)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def verdict(n: int, ci: tuple[float, float], min_trades: int = 30) -> str:
    if n < min_trades:
        return f"Zu wenige Trades ({n}), keine Aussage möglich."
    low, high = ci
    if low > 0:
        return "Ø R positiv und von null unterscheidbar (nur für diese Daten, noch kein Beweis)."
    if high < 0:
        return "Ø R negativ und von null unterscheidbar."
    return "Ø R nicht von null zu unterscheiden."


def buy_and_hold(df: pd.DataFrame, start_idx: int, end_idx: int, cfg: dict) -> float:
    fee, slip = cfg["fee_rate"], cfg["slippage_rate"]
    buy = df["open"].iat[start_idx] * (1 + slip) * (1 + fee)
    sell = df["close"].iat[end_idx - 1] * (1 - slip) * (1 - fee)
    return float(sell / buy - 1)
