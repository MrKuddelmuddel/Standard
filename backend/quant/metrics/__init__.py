"""Performance metrics. Undefined values are None with an explicit reason, never a misleading number.

Definitions (N = number of closed trades, pnl_k = net PnL of trade k, E_t = equity at bar close t, C0 = initial capital):
- net_return            = E_last / C0 - 1
- gross_return          = (E_last + total_fees + total_slippage) / C0 - 1   (before costs, same trades)
- max_drawdown          = max_t (1 - E_t / max_{s<=t} E_s)                  (positive fraction)
- profit_factor         = sum(pnl_k > 0) / |sum(pnl_k < 0)|                 (None if no losing trade)
- win_rate              = count(pnl_k > 0) / N                              (None if N = 0)
- expectancy            = mean(pnl_k)                                       (currency per trade)
- expectancy_r          = mean(r_k) over trades with a stop                 (multiples of initial risk)
- avg_win / avg_loss    = mean of positive / negative pnl_k
- avg_holding_bars      = mean(bars_held); avg_holding_hours = avg_holding_bars * bar length
- total_fees, total_slippage = sums over closed trades
- exposure              = fraction of bars in the window with an open position
"""

from __future__ import annotations

from typing import Any

import numpy as np

MIN_TRADES_FOR_STATISTICS = 30


def compute_metrics(
    trades: list[dict[str, Any]],
    equity: np.ndarray,
    initial_capital: float,
    bar_ms: int,
    bars_in_position: int | None = None,
) -> tuple[dict[str, float | None], dict[str, str]]:
    m: dict[str, float | None] = {}
    notes: dict[str, str] = {}
    n = len(trades)
    pnl = np.array([t["net_pnl"] for t in trades], dtype=float)
    fees = float(sum(t["fees"] for t in trades))
    slip = float(sum(t["slippage_cost"] for t in trades))
    end_equity = float(equity[-1]) if len(equity) else float(initial_capital)
    m["trade_count"] = float(n)
    m["final_equity"] = end_equity
    m["net_return"] = end_equity / initial_capital - 1
    m["gross_return"] = (end_equity + fees + slip) / initial_capital - 1
    m["total_fees"] = fees
    m["total_slippage"] = slip
    if len(equity):
        peak = np.maximum.accumulate(equity)
        m["max_drawdown"] = float(np.max(1 - equity / peak)) if np.all(peak > 0) else 1.0
    else:
        m["max_drawdown"] = None
        notes["max_drawdown"] = "No equity data."
    if n == 0:
        for k in (
            "win_rate",
            "expectancy",
            "expectancy_r",
            "profit_factor",
            "avg_win",
            "avg_loss",
            "avg_holding_bars",
            "avg_holding_hours",
            "largest_loss",
        ):
            m[k] = None
            notes[k] = "No closed trades."
    else:
        wins, losses = pnl[pnl > 0], pnl[pnl < 0]
        m["win_rate"] = float(len(wins) / n)
        m["expectancy"] = float(pnl.mean())
        rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
        m["expectancy_r"] = float(np.mean(rs)) if rs else None
        if not rs:
            notes["expectancy_r"] = "No stop loss defined, so R multiples are not available."
        if len(losses) == 0:
            m["profit_factor"] = None
            notes["profit_factor"] = "No losing trades, profit factor is undefined."
        else:
            m["profit_factor"] = float(wins.sum() / -losses.sum())
        m["avg_win"] = float(wins.mean()) if len(wins) else None
        if not len(wins):
            notes["avg_win"] = "No winning trades."
        m["avg_loss"] = float(losses.mean()) if len(losses) else None
        if not len(losses):
            notes["avg_loss"] = "No losing trades."
        bars = float(np.mean([t["bars_held"] for t in trades]))
        m["avg_holding_bars"] = bars
        m["avg_holding_hours"] = bars * bar_ms / 3_600_000
        m["largest_loss"] = float(pnl.min()) if pnl.min() < 0 else None
    if bars_in_position is not None and len(equity):
        m["exposure"] = bars_in_position / len(equity)
    if 0 < n < MIN_TRADES_FOR_STATISTICS:
        notes["sample_size"] = (
            f"Only {n} trades. Fewer than {MIN_TRADES_FOR_STATISTICS} trades give unreliable statistics."
        )
    return m, notes


def bootstrap_mean_ci(values: list[float], runs: int = 2000, seed: int = 1) -> tuple[float, float] | None:
    """95 % percentile bootstrap interval for the mean. Resamples trades with replacement (fixed seed)."""
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(runs, len(arr)))
    means = arr[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
