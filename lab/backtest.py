"""Der Backtest: geht Kerze für Kerze durch die Daten, ohne in die Zukunft zu sehen.

Annahmen, bewusst vorsichtig:
- Signal am Ende einer Kerze, Einstieg zur Eröffnung der nächsten, plus Slippage.
- Gebühren auf Kauf und Verkauf.
- Berührt eine Kerze Stop und Ziel, zählt der Stop zuerst.
- Springt der Kurs über den Stop hinaus, wird zum schlechteren Eröffnungskurs verkauft.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import risk
from .indicators import atr
from .strategies import Setup, make_setup


@dataclass
class Result:
    trades: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    equity: np.ndarray = field(default_factory=lambda: np.array([]))
    final_equity: float = 0.0


def r_from_prices(entry: float, exit_price: float, stop: float, cfg: dict) -> float:
    """Ergebnis in R: 1 R entspricht dem Risiko bis zum Stop. Gebühren sind abgezogen."""
    risk_per_unit = entry - stop
    cost = cfg["fee_rate"] * (entry + exit_price)
    return ((exit_price - entry) - cost) / risk_per_unit


def simulate_trade(o, h, l, c, entry_idx: int, stop: float, target: float, cfg: dict, last_idx: int):
    """Spielt einen Trade ab Einstiegskerze durch. Gibt (Ausstiegskerze, Preis, Grund) zurück."""
    slip = cfg["slippage_rate"]
    max_bars = cfg["max_bars_in_trade"]
    stop_at = min(last_idx, entry_idx + max_bars - 1)
    for j in range(entry_idx, stop_at + 1):
        if j > entry_idx and o[j] <= stop:
            return j, o[j] * (1 - slip), "Stop (Lücke)"
        if l[j] <= stop:
            return j, stop * (1 - slip), "Stop"
        if h[j] >= target:
            price = target if j == entry_idx else max(target, o[j])
            return j, price, "Ziel"
    return stop_at, c[stop_at] * (1 - slip), "Zeit" if stop_at == entry_idx + max_bars - 1 else "Datenende"


def run_backtest(df: pd.DataFrame, setups: list[Setup], cfg: dict, journal=None, run_id: int | None = None,
                 start_idx: int = 0, end_idx: int | None = None, symbol: str = "BTC/USDT") -> Result:
    end_idx = len(df) if end_idx is None else end_idx
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    day_ids = pd.factorize(df.index.normalize())[0]
    last_idx = end_idx - 1
    pending = {}
    for s in setups:
        if start_idx <= s.idx < last_idx:
            pending.setdefault(s.idx, s)

    fee, slip = cfg["fee_rate"], cfg["slippage_rate"]
    equity = float(cfg["start_capital"])
    pos = None
    last_exit = -10**9
    day, day_start = -1, equity
    res = Result()
    curve = []

    for i in range(start_idx, end_idx):
        if day_ids[i] != day:
            day, day_start = day_ids[i], equity
        s = pending.get(i - 1)
        if s is not None:
            entry = o[i] * (1 + slip)
            state = risk.RiskState(equity, day_start, pos is not None, last_exit)
            dec = risk.review(s, entry, i, state, cfg)
            row = {"ts": s.ts.isoformat(), "symbol": symbol, "strategy": s.strategy, "side": s.side, "entry": entry,
                   "stop": s.stop, "target": s.target, "rr": (s.target - entry) / (entry - s.stop) if entry > s.stop else 0.0,
                   "decision": "TRADE" if dec.ok else "ABGELEHNT", "reasons": json.dumps(dec.reasons(), ensure_ascii=False),
                   "size": dec.size, "risk_amount": dec.risk_amount, "notes": s.note}
            if dec.ok:
                j, xp, why = simulate_trade(o, h, l, c, i, s.stop, s.target, cfg, last_idx)
                fees = fee * (entry * dec.size + xp * dec.size)
                pnl = (xp - entry) * dec.size - fees
                r_mult = pnl / dec.risk_amount
                row.update(exit_ts=df.index[j].isoformat(), exit_price=xp, exit_reason=why, bars_held=j - i + 1,
                           pnl=pnl, fees=fees, r_multiple=r_mult)
                pos = {"exit_idx": j, "pnl": pnl, "size": dec.size, "entry": entry}
                res.trades.append({**row, "r": r_mult, "entry_idx": i, "exit_idx": j})
            elif entry > s.stop:
                j, xp, why = simulate_trade(o, h, l, c, i, s.stop, s.target, cfg, last_idx)
                would = r_from_prices(entry, xp, s.stop, cfg)
                row.update(exit_ts=df.index[j].isoformat(), exit_price=xp, exit_reason=why, bars_held=j - i + 1, would_have_r=would)
                res.rejected.append({**row, "would_have_r": would})
            if journal is not None:
                journal.add_setup(run_id, row)
        if pos is not None and pos["exit_idx"] == i:
            equity += pos["pnl"]
            last_exit = i
            pos = None
        curve.append(equity + (pos["size"] * (c[i] - pos["entry"]) if pos is not None else 0.0))

    res.equity = np.array(curve)
    res.final_equity = equity
    return res


def random_baseline(df: pd.DataFrame, cfg: dict, strat_params: dict, n_setups: int, start_idx: int, end_idx: int,
                    runs: int, seed: int = 1) -> np.ndarray:
    """Dieselbe Ein- und Ausstiegslogik, aber mit zufälligen Einstiegen. Zeigt, was reiner Zufall liefert."""
    rng = np.random.default_rng(seed)
    a = atr(df, strat_params.get("atr_period", 14))
    valid = np.array([i for i in range(start_idx, end_idx - 1) if not np.isnan(a.iat[i])])
    out = []
    if len(valid) == 0 or n_setups == 0:
        return np.array(out)
    for _ in range(runs):
        pick = np.sort(rng.choice(valid, size=min(n_setups, len(valid)), replace=False))
        setups = [make_setup(df, int(i), float(a.iat[i]), strat_params["stop_atr"], strat_params["rr"], "zufall", "Zufallseinstieg", strat_params) for i in pick]
        res = run_backtest(df, setups, cfg, start_idx=start_idx, end_idx=end_idx)
        if res.trades:
            out.append(float(np.mean([t["r"] for t in res.trades])))
    return np.array(out)
