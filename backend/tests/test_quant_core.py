"""Data, schema, indicators, metrics, validation, discovery and provider adapter."""

from __future__ import annotations

import httpx
import numpy as np
import pytest

from quant.data.candles import build_series
from quant.data.csv_import import CsvFormatError, parse_candles_csv
from quant.data.providers.base import ProviderError
from quant.data.providers.binance import BinanceSpotProvider
from quant.data.synthetic import generate
from quant.discovery import SearchConfig, generate_candidates, run_discovery
from quant.indicators import atr, ema, highest_prev, rsi, sma
from quant.metrics import bootstrap_mean_ci
from quant.strategy_schema import canonical_hash, validate_definition
from quant.validation import chronological_splits, run_validation
from tests.conftest import T0, H

EMA_DEF = {
    "name": "EMA",
    "symbols": ["BTCUSDT"],
    "timeframe": "1h",
    "indicators": [
        {"id": "fast", "type": "ema", "period": 10},
        {"id": "slow", "type": "ema", "period": 30},
        {"id": "atr14", "type": "atr", "period": 14},
    ],
    "entry": {"long": {"op": "crosses_above", "left": {"ind": "fast"}, "right": {"ind": "slow"}}},
    "exit": {"long": {"op": "crosses_below", "left": {"ind": "fast"}, "right": {"ind": "slow"}}},
    "risk_management": {"stop_loss": {"type": "atr", "value": 2, "atr_indicator": "atr14"}},
}


# ------------------------------------------------------------------ data
def test_build_series_dedupes_sorts_and_reports_invalid():
    rows = [(T0 + 2 * H, 1, 2, 0.5, 1.5, 1), (T0, 1, 2, 0.5, 1.5, 1), (T0, 9, 9, 9, 9, 9), (T0 + H, 1, 0.5, 2, 1, 1)]
    s, rep = build_series(rows, "BTCUSDT", "1h")
    assert list(s.open_time) == [T0, T0 + 2 * H]
    assert rep.duplicates_removed == 1
    assert len(rep.invalid_rows) == 1
    assert rep.gaps == [{"after": T0, "before": T0 + 2 * H, "missing_bars": 1}]


def test_csv_import_accepts_iso_seconds_and_ms():
    text = "timestamp,open,high,low,close,volume\n2024-01-01T00:00:00Z,1,2,0.5,1.5,10\n1704070800,1,2,0.5,1.5,10\n1704074400000,1,2,0.5,1.5,10\nbad,1,2,3,4,5\n"
    s, rep = parse_candles_csv(text, "BTCUSDT", "1h")
    assert len(s) == 3 and rep.gaps == []
    assert rep.invalid_rows[0]["line"] == 5


def test_csv_import_missing_columns():
    with pytest.raises(CsvFormatError, match="Missing columns"):
        parse_candles_csv("timestamp,open,close\n1,2,3\n", "BTCUSDT", "1h")


def test_synthetic_is_flagged_and_deterministic():
    a, b = generate(bars=500, seed=1), generate(bars=500, seed=1)
    assert a.synthetic and a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != generate(bars=500, seed=2).fingerprint()


# ------------------------------------------------------------------ schema
def test_schema_valid_and_hash_is_canonical():
    d1, issues = validate_definition(EMA_DEF)
    assert not issues and d1 is not None
    reordered = dict(reversed(list(EMA_DEF.items())))
    d2, _ = validate_definition(reordered)
    assert d2 is not None and canonical_hash(d1) == canonical_hash(d2)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda d: d.update(schema_version="2.0"), "Unsupported schema_version"),
        (lambda d: d.update(timeframe="3m"), "timeframe"),
        (lambda d: d["entry"]["long"].update(op="eval"), "op"),
        (lambda d: d["indicators"].append({"id": "fast", "type": "ema", "period": 5}), "unique"),
        (lambda d: d["indicators"][0].update(period=1), "period"),
        (lambda d: d.update(symbols=["DOGEUSDT"]), "symbols"),
        (
            lambda d: d["entry"].update(long={"op": "gt", "left": {"ind": "nope"}, "right": {"value": 1}}),
            "unknown indicator",
        ),
        (lambda d: d.update(market_type="margin"), "market_type"),
        (lambda d: d.update(extra_field=1), "extra"),
    ],
)
def test_schema_rejects_invalid(mutate, expected):
    import copy

    data = copy.deepcopy(EMA_DEF)
    mutate(data)
    defn, issues = validate_definition(data)
    assert defn is None
    assert any(expected.lower() in (i.path + " " + i.message).lower() for i in issues), issues


def test_schema_limits_nesting_depth():
    cond = {"op": "gt", "left": {"price": "close"}, "right": {"value": 1}}
    for _ in range(6):
        cond = {"not": cond}
    data = {**EMA_DEF, "entry": {"long": cond}}
    defn, issues = validate_definition(data)
    assert defn is None and any("nested too deeply" in i.message for i in issues)


# ------------------------------------------------------------------ indicators
def test_indicators_against_reference_values():
    x = np.arange(1.0, 11.0)
    np.testing.assert_allclose(sma(x, 3)[2:], [2, 3, 4, 5, 6, 7, 8, 9])
    e = ema(x, 3)
    assert np.isnan(e[1]) and e[2] == pytest.approx(2.0) and e[3] == pytest.approx(3.0)
    up = np.arange(1.0, 30.0)
    assert rsi(up, 14)[-1] == pytest.approx(100.0)
    assert np.isnan(rsi(up, 14)[13])
    h = np.array([1, 5, 3, 4, 2.0])
    np.testing.assert_allclose(highest_prev(h, 2), [np.nan, np.nan, 5, 5, 4], equal_nan=True)
    hi, lo, cl = np.full(20, 11.0), np.full(20, 9.0), np.full(20, 10.0)
    assert atr(hi, lo, cl, 14)[-1] == pytest.approx(2.0)


# ------------------------------------------------------------------ metrics
def test_bootstrap_ci_deterministic_and_none_for_tiny_samples():
    vals = list(np.random.default_rng(1).normal(0.1, 1, 50))
    assert bootstrap_mean_ci(vals, 300, seed=4) == bootstrap_mean_ci(vals, 300, seed=4)
    assert bootstrap_mean_ci([1.0]) is None


# ------------------------------------------------------------------ validation
def test_chronological_splits_do_not_overlap():
    segs = chronological_splits(100, 1100, 0.6, 0.2)
    assert [(s.start, s.end) for s in segs] == [(100, 700), (700, 900), (900, 1100)]
    with pytest.raises(ValueError):
        chronological_splits(0, 100, 0.8, 0.3)


def test_validation_report_has_all_sections_and_warnings():
    defn, _ = validate_definition(EMA_DEF)
    assert defn
    rep = run_validation(generate(bars=6000, seed=2), defn, folds=3)
    assert set(rep.results["splits"]) == {"train", "validation", "test"}
    assert len(rep.results["walk_forward"]) == 3
    assert rep.results["cost_sensitivity"]["multiplier"] == 2.0
    assert rep.results["parameter_stability"]
    assert rep.segments[0]["end_index"] == rep.segments[1]["start_index"]


# ------------------------------------------------------------------ discovery
def test_discovery_dedupes_rejects_and_never_ranks_on_test():
    cfg = SearchConfig(
        templates=["ema_cross", "breakout"],
        max_candidates=40,
        min_trades=10,
        params={
            "ema_fast": [10, 10, 20],
            "ema_slow": [50],
            "stop_atr": [2.0],
            "take_profit_r": [2.0],
            "breakout_lookback": [20, 40],
        },
    )
    raw = generate_candidates(cfg)
    res = run_discovery(generate(bars=6000, seed=4), cfg)
    assert res.duplicates == 1 and res.generated == len(raw)
    assert all(c.rejection_reason for c in res.candidates if c.status == "rejected")
    for c in res.candidates:
        if c.test:
            assert c.status == "validated"  # test segment only touched for validated candidates
        if c.score is not None:
            assert c.validation
    assert len({c.hash for c in res.candidates}) == len(res.candidates)


def test_discovery_respects_cancel_and_is_deterministic():
    cfg = SearchConfig(templates=["ema_cross"], max_candidates=12, min_trades=5)
    s = generate(bars=4000, seed=8)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    assert run_discovery(s, cfg, should_cancel=cancel).stopped_early == "cancelled"
    a, b = run_discovery(s, cfg), run_discovery(s, cfg)
    assert [(c.hash, c.status, c.score) for c in a.candidates] == [(c.hash, c.status, c.score) for c in b.candidates]


# ------------------------------------------------------------------ provider (mocked, no network)
def _kline(t: int) -> list:
    return [t, "1.0", "2.0", "0.5", "1.5", "10", t + H - 1, "0", 1, "0", "0", "0"]


def test_binance_pagination_and_parsing():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        start = int(req.url.params["startTime"])
        calls.append(start)
        first = T0 + -(-(start - T0) // H) * H  # like the exchange: first candle opening at or after startTime
        batch = [_kline(first + k * H) for k in range(2)] if first < T0 + 4 * H else []
        return httpx.Response(200, json=batch)

    p = BinanceSpotProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)), page_limit=2, sleep=lambda s: None
    )
    rows = p.fetch_historical_candles("BTCUSDT", "1h", T0, T0 + 5 * H)
    assert [r[0] for r in rows] == [T0 + k * H for k in range(4)]
    assert rows[0][1:] == [1.0, 2.0, 0.5, 1.5, 10.0]


def test_binance_retries_on_429_then_fails_cleanly():
    attempts = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "1"})

    p = BinanceSpotProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=2, sleep=lambda s: None
    )
    with pytest.raises(ProviderError, match="429"):
        p.fetch_historical_candles("BTCUSDT", "1h", T0, T0 + H)
    assert attempts["n"] == 3
    assert not p.health_check().ok


def test_binance_rejects_unsupported_symbol():
    p = BinanceSpotProvider(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))))
    with pytest.raises(ProviderError, match="not supported"):
        p.fetch_historical_candles("DOGEUSDT", "1h", T0, T0 + H)


def test_metrics_report_bootstrap_interval_around_mean():
    import numpy as np

    from quant.metrics import compute_metrics

    trades = [
        {"net_pnl": v, "fees": 1.0, "slippage_cost": 0.5, "bars_held": 3} for v in (10.0, -5.0, 20.0, -8.0, 3.0, 7.0)
    ]
    m, notes = compute_metrics(trades, np.array([10_000.0, 10_027.0]), 10_000.0, 3_600_000)
    assert m["expectancy_ci_low"] is not None and m["expectancy_ci_high"] is not None
    assert m["expectancy_ci_low"] <= m["expectancy"] <= m["expectancy_ci_high"]
    assert "bootstrap" in notes["expectancy_ci_low"]
