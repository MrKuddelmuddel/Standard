"""Backtest runner built on the shared Simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .. import ENGINE_VERSION, EXECUTION_MODEL_VERSION
from ..data.candles import CandleSeries, validate_series
from ..metrics import compute_metrics
from ..strategy_schema.model import StrategyDefinition, canonical_hash
from .signals import SignalSet, build_signals
from .simulator import SimState, Simulator, equity_drawdown

MAX_BARS = 300_000


class BacktestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class BacktestResult:
    trades: list[dict[str, Any]]
    equity: np.ndarray
    drawdown: np.ndarray
    times: np.ndarray
    metrics: dict[str, float | None]
    metric_notes: dict[str, str]
    warnings: list[str]
    config: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)


def resolve_window(
    series: CandleSeries, defn: StrategyDefinition, start_index: int | None, end_index: int | None
) -> tuple[int, int]:
    warm = defn.warmup_bars()
    start = max(warm, start_index or 0)
    end = len(series) if end_index is None else min(end_index, len(series))
    if end - start < 2:
        raise BacktestError(
            "insufficient_data",
            f"Need at least {warm + 2} bars (indicator warm-up {warm}); window has {max(0, end - start)} usable bars.",
        )
    return start, end


def run_backtest(
    series: CandleSeries,
    defn: StrategyDefinition,
    initial_capital: float = 10_000.0,
    *,
    start_index: int | None = None,
    end_index: int | None = None,
    fee_bps: float | None = None,
    slippage_bps: float | None = None,
    signals: SignalSet | None = None,
    keep_events: bool = False,
) -> BacktestResult:
    if len(series) > MAX_BARS:
        raise BacktestError("too_many_bars", f"Dataset has {len(series)} bars, the limit is {MAX_BARS}.")
    if initial_capital <= 0:
        raise BacktestError("invalid_capital", "Initial capital must be positive.")
    if series.timeframe != defn.timeframe:
        raise BacktestError("timeframe_mismatch", f"Strategy uses {defn.timeframe}, data is {series.timeframe}.")
    start, end = resolve_window(series, defn, start_index, end_index)
    sig = signals or build_signals(series, defn)
    sim = Simulator(series, defn, sig, initial_capital, end, fee_bps, slippage_bps, SimState(realized=initial_capital))
    trades: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    equity = np.empty(end - start)
    in_pos = 0
    for k, i in enumerate(range(start, end)):
        out = sim.process_bar(i)
        equity[k] = out.equity
        trades.extend(out.trades)
        if sim.state.position is not None:
            in_pos += 1
        if keep_events:
            events.extend(out.events)
    warnings: list[str] = []
    gaps, misaligned = validate_series(series)
    window_gaps = [g for g in gaps if series.open_time[start] <= g["after"] < series.open_time[end - 1]]
    if window_gaps:
        warnings.append(
            f"Data has {len(window_gaps)} gap(s) inside the test window. Results around gaps are unreliable."
        )
    if series.synthetic:
        warnings.append("Synthetic demo data: results say nothing about real markets.")
    if defn.market_type == "futures_sim":
        warnings.append("Futures simulation without funding payments: funding costs are not modeled.")
    if (fee_bps if fee_bps is not None else defn.costs.fee_bps) == 0 or (
        slippage_bps if slippage_bps is not None else defn.costs.slippage_bps
    ) == 0:
        warnings.append("Fees or slippage are set to zero. Real trading always has costs.")
    if sim.state.bankrupt:
        warnings.append("Capital was exhausted during the backtest.")
    if trades and trades[-1]["exit_reason"] == "end_of_period":
        warnings.append("The last trade was closed at the end of the window, not by a rule.")
    metrics, notes = compute_metrics(trades, equity, initial_capital, series.bar_ms, in_pos)
    if not trades:
        warnings.append("No trades were generated in this window.")
    config = {
        "engine_version": ENGINE_VERSION,
        "execution_model_version": EXECUTION_MODEL_VERSION,
        "strategy_hash": canonical_hash(defn),
        "data_fingerprint": series.fingerprint(),
        "symbol": series.symbol,
        "timeframe": series.timeframe,
        "start_index": start,
        "end_index": end,
        "start_time": int(series.open_time[start]),
        "end_time": int(series.open_time[end - 1]),
        "initial_capital": initial_capital,
        "fee_bps": defn.costs.fee_bps if fee_bps is None else fee_bps,
        "slippage_bps": defn.costs.slippage_bps if slippage_bps is None else slippage_bps,
        "fee_model": "bps_of_notional_per_fill",
        "slippage_model": "fixed_bps_adverse_on_market_and_stop_fills",
        "intrabar_rule": "stop_first",
        "synthetic_data": series.synthetic,
    }
    return BacktestResult(
        trades,
        equity,
        equity_drawdown(equity),
        series.open_time[start:end].copy(),
        metrics,
        notes,
        warnings,
        config,
        events,
    )
