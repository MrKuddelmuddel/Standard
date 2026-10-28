"""Overfitting guard: chronological splits, out-of-sample tests, rolling windows, cost and parameter sensitivity.

Indicators are causal, so computing them on the full series and trading only inside a window does not leak
future data into the window. Positions are force-closed at the end of each window.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ..data.candles import CandleSeries
from ..engine import BacktestError, resolve_window, run_backtest
from ..engine.signals import build_signals
from ..metrics import MIN_TRADES_FOR_STATISTICS
from ..strategy_schema.model import StrategyDefinition

KEY_METRICS = ("net_return", "max_drawdown", "profit_factor", "win_rate", "trade_count", "expectancy", "expectancy_r")


@dataclass
class Segment:
    name: str
    start: int
    end: int

    def to_dict(self, series: CandleSeries) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_index": self.start,
            "end_index": self.end,
            "start_time": int(series.open_time[self.start]),
            "end_time": int(series.open_time[self.end - 1]),
            "bars": self.end - self.start,
        }


def chronological_splits(start: int, end: int, train: float = 0.6, validation: float = 0.2) -> list[Segment]:
    if not (0 < train < 1 and 0 <= validation < 1 and train + validation < 1):
        raise ValueError("Split fractions must be positive and sum to less than 1.")
    n = end - start
    a = start + int(n * train)
    b = a + int(n * validation)
    segs = [Segment("train", start, a)]
    if validation > 0:
        segs.append(Segment("validation", a, b))
    segs.append(Segment("test", b, end))
    return segs


def rolling_windows(start: int, end: int, folds: int) -> list[Segment]:
    n = end - start
    size = n // folds
    return [
        Segment(f"fold_{k + 1}", start + k * size, start + (k + 1) * size if k < folds - 1 else end)
        for k in range(folds)
    ]


def _metrics(
    series: CandleSeries,
    defn: StrategyDefinition,
    seg: Segment,
    capital: float,
    signals=None,
    fee_bps: float | None = None,
    slippage_bps: float | None = None,
) -> dict[str, Any]:
    try:
        r = run_backtest(
            series,
            defn,
            capital,
            start_index=seg.start,
            end_index=seg.end,
            signals=signals,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
    except BacktestError as exc:
        return {"error": exc.code, "message": str(exc)}
    return {k: r.metrics.get(k) for k in KEY_METRICS}


def perturbations(defn: StrategyDefinition, rel: float = 0.2) -> list[tuple[str, StrategyDefinition]]:
    """Neighbouring parameter sets: each indicator period moved by +-rel (at least +-1)."""
    out: list[tuple[str, StrategyDefinition]] = []
    for idx, ind in enumerate(defn.indicators):
        step = max(1, round(ind.period * rel))
        for delta in (-step, step):
            p = ind.period + delta
            if p < 2 or p > 500:
                continue
            data = copy.deepcopy(defn.model_dump(mode="json", by_alias=True))
            data["indicators"][idx]["period"] = p
            try:
                out.append((f"{ind.id}.period={p}", StrategyDefinition.model_validate(data)))
            except ValueError:
                continue
    return out


@dataclass
class ValidationReport:
    method: str
    segments: list[dict[str, Any]]
    results: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    status: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "segments": self.segments,
            "results": self.results,
            "warnings": self.warnings,
            "status": self.status,
        }


def run_validation(
    series: CandleSeries,
    defn: StrategyDefinition,
    capital: float = 10_000.0,
    *,
    train: float = 0.6,
    validation: float = 0.2,
    folds: int = 4,
    cost_multiplier: float = 2.0,
    min_trades: int = MIN_TRADES_FOR_STATISTICS,
) -> ValidationReport:
    start, end = resolve_window(series, defn, None, None)
    signals = build_signals(series, defn)
    segs = chronological_splits(start, end, train, validation)
    results: dict[str, Any] = {"splits": {}, "walk_forward": [], "cost_sensitivity": {}, "parameter_stability": []}
    warnings: list[str] = []
    for seg in segs:
        results["splits"][seg.name] = _metrics(series, defn, seg, capital, signals)
    tr, te = results["splits"].get("train", {}), results["splits"].get("test", {})
    oos_name = "validation" if "validation" in results["splits"] else "test"
    oos = results["splits"][oos_name]
    for name, res in results["splits"].items():
        if "error" in res:
            warnings.append(f"{name}: {res['message']}")
        elif (res.get("trade_count") or 0) < min_trades:
            warnings.append(
                f"{name}: only {int(res.get('trade_count') or 0)} trades (< {min_trades}), too few for reliable statistics."
            )
    if "error" not in tr and "error" not in oos:
        tr_exp, oos_exp = tr.get("expectancy"), oos.get("expectancy")
        if tr_exp is not None and oos_exp is not None and tr_exp > 0 and oos_exp <= 0:
            warnings.append(
                f"Unstable: positive expectancy in train but not in {oos_name}. Typical sign of overfitting."
            )
        if (tr.get("net_return") or 0) > 0 and (oos.get("net_return") or 0) < 0.5 * (tr.get("net_return") or 0) * (
            (oos.get("trade_count") or 0) / max(1.0, tr.get("trade_count") or 1)
        ):
            warnings.append(f"Return in {oos_name} drops sharply relative to train (adjusted for trade count).")
    if "error" not in te and (te.get("net_return") or 0) < 0 and (tr.get("net_return") or 0) > 0:
        warnings.append("Test period is negative while train is positive.")
    eval_seg = Segment("all_out_of_sample", segs[1].start if len(segs) > 1 else start, end)
    for seg in rolling_windows(start, end, folds):
        results["walk_forward"].append({**seg.to_dict(series), **_metrics(series, defn, seg, capital, signals)})
    wf = [f for f in results["walk_forward"] if "error" not in f and f.get("trade_count")]
    if wf:
        positive = sum(1 for f in wf if (f.get("net_return") or 0) > 0)
        results["walk_forward_summary"] = {
            "folds_with_trades": len(wf),
            "profitable_folds": positive,
            "note": "Rolling windows with fixed parameters (no re-optimization).",
        }
        if positive < len(wf) / 2:
            warnings.append(f"Only {positive} of {len(wf)} rolling windows were profitable.")
    base = _metrics(series, defn, eval_seg, capital, signals)
    stressed = _metrics(
        series,
        defn,
        eval_seg,
        capital,
        signals,
        fee_bps=defn.costs.fee_bps * cost_multiplier,
        slippage_bps=defn.costs.slippage_bps * cost_multiplier,
    )
    results["cost_sensitivity"] = {
        "window": eval_seg.to_dict(series),
        "multiplier": cost_multiplier,
        "base": base,
        "stressed": stressed,
    }
    if (
        "error" not in base
        and "error" not in stressed
        and (base.get("net_return") or 0) > 0 >= (stressed.get("net_return") or 0)
    ):
        warnings.append(f"Cost sensitive: profitable at assumed costs, not at {cost_multiplier:g}x costs.")
    train_seg = segs[0]
    exps = []
    for label, alt in perturbations(defn):
        res = _metrics(series, alt, train_seg, capital)
        results["parameter_stability"].append({"change": label, **res})
        if "error" not in res and res.get("expectancy") is not None:
            exps.append(res["expectancy"])
    if exps and tr.get("expectancy") is not None:
        flips = sum(1 for e in exps if (e > 0) != ((tr.get("expectancy") or 0) > 0))
        results["parameter_stability_summary"] = {"neighbours": len(exps), "sign_flips": flips}
        if flips > len(exps) / 3:
            warnings.append(
                f"Parameter sensitive: {flips} of {len(exps)} neighbouring parameter sets flip the sign of expectancy."
            )
    return ValidationReport("split+walk_forward+sensitivity_v1", [s.to_dict(series) for s in segs], results, warnings)
