"""Engine correctness: execution timing, costs, stops, sizing, shorts, edge cases, leakage, determinism."""

from __future__ import annotations

import numpy as np
import pytest

from quant.data.synthetic import generate
from quant.engine import BacktestError, run_backtest
from quant.engine.signals import build_signals
from quant.strategy_schema.model import StrategyDefinition, canonical_hash
from tests.conftest import defn, flat, make_series

ALWAYS = {"op": "gt", "left": {"price": "close"}, "right": {"value": 0}}


def signal_at(price: float) -> dict:
    """Entry fires on the bar whose close is above `price`."""
    return {"op": "gt", "left": {"price": "close"}, "right": {"value": price}}


def test_entry_fills_at_next_open_not_signal_close():
    rows = flat(3) + [(100, 106, 99, 105)] + [(110, 110.5, 109.5, 110)] * 4
    s = make_series(rows)
    r = run_backtest(s, defn(entry={"long": signal_at(104)}), 10_000)
    t = r.trades[0]
    assert t["entry_index"] == 4
    assert t["entry_price"] == pytest.approx(110.0)


def test_fees_charged_on_both_fills_and_reduce_equity():
    s = make_series(flat(2) + [(100, 101, 99.9, 100.5)] + flat(5))
    d = defn(entry={"long": signal_at(100.2)}, costs={"fee_bps": 10, "slippage_bps": 0})
    r = run_backtest(s, d, 10_000)
    t = r.trades[0]
    notional = t["quantity"] * 100
    assert t["fees"] == pytest.approx(notional * 0.001 * 2)
    assert t["net_pnl"] == pytest.approx(-t["fees"])
    assert r.metrics["final_equity"] == pytest.approx(10_000 - t["fees"])
    assert t["gross_pnl"] == pytest.approx(0.0, abs=1e-9)


def test_slippage_is_adverse_and_accounted():
    s = make_series(flat(2) + [(100, 101, 99.9, 100.5)] + flat(5))
    d = defn(entry={"long": signal_at(100.2)}, costs={"fee_bps": 0, "slippage_bps": 50})
    t = run_backtest(s, d, 10_000).trades[0]
    assert t["entry_price"] == pytest.approx(100 * 1.005)
    assert t["exit_price"] == pytest.approx(100 * 0.995)
    assert t["slippage_cost"] == pytest.approx(t["quantity"] * 1.0)
    assert t["net_pnl"] == pytest.approx(-t["slippage_cost"])


def test_stop_wins_when_bar_touches_stop_and_target():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + [(100, 130, 70, 100)] + flat(3)
    d = defn(
        entry={"long": signal_at(100.2)},
        risk_management={
            "stop_loss": {"type": "percent", "value": 10},
            "take_profit": {"type": "percent", "value": 10},
        },
    )
    t = run_backtest(make_series(rows), d, 10_000).trades[0]
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_price"] == pytest.approx(90.0)


def test_gap_through_stop_fills_at_worse_open():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + [(100, 100.2, 99.8, 100)] + [(80, 81, 79, 80)] + flat(2, 80)
    d = defn(entry={"long": signal_at(100.2)}, risk_management={"stop_loss": {"type": "percent", "value": 5}})
    t = run_backtest(make_series(rows), d, 10_000).trades[0]
    assert t["exit_reason"] == "stop_gap"
    assert t["exit_price"] == pytest.approx(80.0)


def test_take_profit_fills_at_target_without_bonus():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + [(100, 100.2, 99.8, 100)] + [(120, 125, 119, 124)] + flat(2, 124)
    d = defn(entry={"long": signal_at(100.2)}, risk_management={"take_profit": {"type": "percent", "value": 5}})
    t = run_backtest(make_series(rows), d, 10_000).trades[0]
    assert t["exit_reason"] == "take_profit"
    assert t["exit_price"] == pytest.approx(105.0)


def test_exit_signal_executes_next_open():
    rows = (
        flat(2)
        + [(100, 101, 99.9, 100.5)]
        + [(100, 100.2, 99.8, 100)] * 2
        + [(100, 100.1, 95, 96)]
        + [(97, 97.5, 96.5, 97)] * 2
    )
    d = defn(
        entry={"long": signal_at(100.2)},
        exit={"long": {"op": "lt", "left": {"price": "close"}, "right": {"value": 97}}},
    )
    t = run_backtest(make_series(rows), d, 10_000).trades[0]
    assert t["exit_reason"] == "exit_signal"
    assert t["exit_index"] == 6
    assert t["exit_price"] == pytest.approx(97.0)


def test_max_bars_exit():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + flat(10)
    d = defn(entry={"long": signal_at(100.2)}, risk_management={"max_bars_in_trade": 3})
    t = run_backtest(make_series(rows), d, 10_000).trades[0]
    assert t["exit_reason"] == "max_bars"
    assert t["bars_held"] == 4  # three bars held, exit at the next open


def test_end_of_period_close_and_warning():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + flat(3)
    r = run_backtest(make_series(rows), defn(entry={"long": signal_at(100.2)}), 10_000)
    assert r.trades[-1]["exit_reason"] == "end_of_period"
    assert any("end of the window" in w for w in r.warnings)


def test_no_trades_gives_none_metrics_not_zero():
    r = run_backtest(make_series(flat(20)), defn(), 10_000)
    assert r.metrics["trade_count"] == 0
    for k in ("win_rate", "profit_factor", "expectancy"):
        assert r.metrics[k] is None
        assert k in r.metric_notes
    assert r.metrics["net_return"] == 0


def test_profit_factor_undefined_without_losses():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + [(110, 111, 109, 110)] * 4
    r = run_backtest(make_series(rows), defn(entry={"long": signal_at(100.2)}), 10_000)
    assert r.metrics["profit_factor"] is None
    assert "No losing trades" in r.metric_notes["profit_factor"]


def test_risk_percent_sizing_risks_one_percent():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + [(100, 100.2, 99.8, 100)] + [(100, 100.1, 89, 90)] + flat(2, 90)
    d = defn(
        entry={"long": signal_at(100.2)},
        risk_management={"stop_loss": {"type": "percent", "value": 10}},
        position_sizing={"type": "risk_percent", "risk_percent": 1, "fraction": 1},
    )
    t = run_backtest(make_series(rows), d, 10_000).trades[0]
    assert t["quantity"] == pytest.approx(10.0)  # 100 risk / 10 stop distance
    assert t["net_pnl"] == pytest.approx(-100.0)
    assert t["r_multiple"] == pytest.approx(-1.0)


def test_fixed_fraction_never_exceeds_capital_including_fee():
    rows = flat(2) + [(100, 101, 99.9, 100.5)] + flat(4)
    d = defn(entry={"long": signal_at(100.2)}, costs={"fee_bps": 10, "slippage_bps": 0})
    t = run_backtest(make_series(rows), d, 10_000).trades[0]
    assert t["quantity"] * 100 * 1.001 <= 10_000 + 1e-6


def test_short_profits_when_price_falls_in_futures_sim():
    rows = flat(2) + [(100, 100.1, 99, 99.5)] + [(100, 100.2, 99.8, 100)] + [(90, 90.5, 89.5, 90)] * 3
    d = defn(
        market_type="futures_sim",
        direction="short",
        entry={"short": {"op": "lt", "left": {"price": "close"}, "right": {"value": 99.8}}},
    )
    r = run_backtest(make_series(rows), d, 10_000)
    t = r.trades[0]
    assert t["side"] == "short" and t["net_pnl"] > 0
    assert any("funding" in w for w in r.warnings)


def test_short_on_spot_is_rejected_by_schema():
    with pytest.raises(ValueError, match="futures_sim"):
        defn(direction="short", entry={"short": ALWAYS})


def test_insufficient_data_error():
    d = defn(
        indicators=[{"id": "e", "type": "ema", "period": 50}],
        entry={"long": {"op": "gt", "left": {"price": "close"}, "right": {"ind": "e"}}},
    )
    with pytest.raises(BacktestError) as exc:
        run_backtest(make_series(flat(30)), d, 10_000)
    assert exc.value.code == "insufficient_data"


def test_timeframe_mismatch_error():
    with pytest.raises(BacktestError) as exc:
        run_backtest(make_series(flat(30)), defn(timeframe="4h"), 10_000)
    assert exc.value.code == "timeframe_mismatch"


def test_signals_do_not_depend_on_future_data():
    s = generate(bars=3000, seed=3)
    d = StrategyDefinition.model_validate(
        {
            "name": "x",
            "symbols": ["BTCUSDT"],
            "timeframe": "1h",
            "indicators": [
                {"id": "f", "type": "ema", "period": 12},
                {"id": "sl", "type": "sma", "period": 40},
                {"id": "r", "type": "rsi", "period": 14},
                {"id": "a", "type": "atr", "period": 14},
                {"id": "hi", "type": "highest", "period": 20},
            ],
            "entry": {
                "long": {
                    "all": [
                        {"op": "crosses_above", "left": {"ind": "f"}, "right": {"ind": "sl"}},
                        {"op": "lt", "left": {"ind": "r"}, "right": {"value": 70}},
                    ]
                }
            },
        }
    )
    cut = 2000
    from quant.data.candles import build_series

    rows = list(
        zip(
            s.open_time[:cut].tolist(),
            s.open[:cut],
            s.high[:cut],
            s.low[:cut],
            s.close[:cut],
            s.volume[:cut],
            strict=True,
        )
    )
    part, _ = build_series(rows, "BTCUSDT", "1h")
    full_sig, part_sig = build_signals(s, d), build_signals(part, d)
    assert np.array_equal(full_sig.entry_long[:cut], part_sig.entry_long)
    for k in full_sig.indicators:
        np.testing.assert_allclose(full_sig.indicators[k][:cut], part_sig.indicators[k], equal_nan=True)


def test_backtest_is_reproducible_and_bound_to_inputs():
    s = generate(bars=4000, seed=5)
    d = StrategyDefinition.model_validate(
        {
            "name": "x",
            "symbols": ["BTCUSDT"],
            "timeframe": "1h",
            "indicators": [{"id": "f", "type": "ema", "period": 10}, {"id": "s", "type": "ema", "period": 30}],
            "entry": {"long": {"op": "crosses_above", "left": {"ind": "f"}, "right": {"ind": "s"}}},
            "exit": {"long": {"op": "crosses_below", "left": {"ind": "f"}, "right": {"ind": "s"}}},
        }
    )
    a, b = run_backtest(s, d), run_backtest(s, d)
    assert a.trades == b.trades
    assert np.array_equal(a.equity, b.equity)
    assert a.config["strategy_hash"] == canonical_hash(d)
    assert a.config["data_fingerprint"] == generate(bars=4000, seed=5).fingerprint()
    assert a.config["data_fingerprint"] != generate(bars=4000, seed=6).fingerprint()


def test_equity_consistent_with_trade_pnl():
    s = generate(bars=5000, seed=9)
    d = StrategyDefinition.model_validate(
        {
            "name": "x",
            "symbols": ["BTCUSDT"],
            "timeframe": "1h",
            "indicators": [
                {"id": "f", "type": "ema", "period": 10},
                {"id": "s", "type": "ema", "period": 30},
                {"id": "a", "type": "atr", "period": 14},
            ],
            "entry": {"long": {"op": "crosses_above", "left": {"ind": "f"}, "right": {"ind": "s"}}},
            "risk_management": {
                "stop_loss": {"type": "atr", "value": 2, "atr_indicator": "a"},
                "take_profit": {"type": "r_multiple", "value": 2},
            },
        }
    )
    r = run_backtest(s, d)
    assert r.trades
    assert r.metrics["final_equity"] == pytest.approx(10_000 + sum(t["net_pnl"] for t in r.trades))
    for t in r.trades:
        assert t["gross_pnl"] == pytest.approx(t["net_pnl"] + t["fees"] + t["slippage_cost"])
    assert (r.drawdown <= 1e-12).all()
