import json
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import data as D  # noqa: E402
from lab import metrics as M  # noqa: E402
from lab import risk  # noqa: E402
from lab.backtest import r_from_prices, run_backtest  # noqa: E402
from lab.journal import Journal  # noqa: E402
from lab.strategies import REGISTRY, Setup  # noqa: E402

CFG = {"start_capital": 10000, "fee_rate": 0.001, "slippage_rate": 0.0005, "risk_per_trade": 0.01, "max_daily_loss": 0.03,
       "min_rr": 1.5, "max_cost_ratio": 0.25, "max_position_pct": 5.0, "max_bars_in_trade": 10, "cooldown_bars": 1}


def frame(rows):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="60min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


def setup(df, idx, stop, target):
    return Setup(idx=idx, ts=df.index[idx], strategy="test", ref_price=float(df["close"].iat[idx]), stop=stop, target=target)


FLAT = (100, 100.2, 99.8, 100, 1)


class BacktestRules(unittest.TestCase):
    def test_entry_uses_next_open_not_signal_close(self):
        df = frame([FLAT, (100, 100, 100, 100, 1), (105, 105.2, 104.9, 105, 1)] + [(105, 105.2, 104.9, 105, 1)] * 5)
        res = run_backtest(df, [setup(df, 1, 95, 130)], CFG)
        self.assertEqual(len(res.trades), 1)
        self.assertAlmostEqual(res.trades[0]["entry"], 105 * (1 + CFG["slippage_rate"]), places=6)

    def test_stop_counts_first_when_bar_touches_both(self):
        df = frame([FLAT, FLAT, (100, 130, 80, 100, 1), FLAT, FLAT])
        res = run_backtest(df, [setup(df, 0, 90, 120)], CFG)
        self.assertEqual(res.trades[0]["exit_reason"], "Stop")

    def test_gap_below_stop_exits_at_worse_open(self):
        df = frame([FLAT, FLAT, (99.9, 100.1, 99.8, 100, 1), (80, 81, 79, 80, 1), FLAT])
        res = run_backtest(df, [setup(df, 0, 95, 120)], CFG)
        t = res.trades[0]
        self.assertEqual(t["exit_reason"], "Stop (Lücke)")
        self.assertLess(t["exit_price"], 95)

    def test_costs_make_a_flat_trade_a_loss(self):
        df = frame([FLAT] * 20)
        res = run_backtest(df, [setup(df, 0, 95, 120)], CFG)
        self.assertEqual(res.trades[0]["exit_reason"], "Zeit")
        self.assertLess(res.trades[0]["pnl"], 0)
        self.assertGreater(res.trades[0]["fees"], 0)

    def test_risk_amount_is_one_percent_of_equity(self):
        df = frame([FLAT] * 6)
        res = run_backtest(df, [setup(df, 0, 95, 110)], CFG)
        self.assertAlmostEqual(res.trades[0]["risk_amount"], CFG["start_capital"] * CFG["risk_per_trade"], places=6)

    def test_no_second_position_while_one_is_open(self):
        df = frame([FLAT] * 12)
        res = run_backtest(df, [setup(df, 0, 95, 120), setup(df, 2, 95, 120)], CFG)
        self.assertEqual(len(res.trades), 1)
        self.assertEqual(len(res.rejected), 1)
        self.assertIn("Position", res.rejected[0]["reasons"])

    def test_last_bar_signal_is_ignored(self):
        df = frame([FLAT] * 5)
        res = run_backtest(df, [setup(df, 4, 95, 120)], CFG)
        self.assertEqual(len(res.trades) + len(res.rejected), 0)


class Titan(unittest.TestCase):
    def state(self, **kw):
        base = dict(equity=10000, day_start_equity=10000, in_position=False, last_exit_idx=-100)
        base.update(kw)
        return risk.RiskState(**base)

    def make(self, stop=95, target=110):
        return Setup(idx=5, ts=pd.Timestamp("2024-01-01", tz="UTC"), strategy="t", ref_price=100, stop=stop, target=target)

    def test_low_reward_is_rejected(self):
        d = risk.review(self.make(target=102), 100, 10, self.state(), CFG)
        self.assertFalse(d.ok)
        self.assertTrue(any("Risk/Reward" in r for r in d.reasons()))

    def test_daily_loss_limit_blocks(self):
        d = risk.review(self.make(), 100, 10, self.state(equity=9600), CFG)
        self.assertFalse(d.ok)
        self.assertTrue(any("Tageslimit" in r for r in d.reasons()))

    def test_costs_vs_risk_blocks_tiny_stops(self):
        d = risk.review(self.make(stop=99.9, target=100.3), 100, 10, self.state(), CFG)
        self.assertFalse(d.ok)
        self.assertTrue(any("Kosten" in r for r in d.reasons()))

    def test_stress_costs_do_not_change_titans_decision(self):
        stress = dict(CFG, decision_fee_rate=CFG["fee_rate"], decision_slippage_rate=CFG["slippage_rate"],
                      fee_rate=CFG["fee_rate"] * 4, slippage_rate=CFG["slippage_rate"] * 4)
        base = risk.review(self.make(stop=98.8, target=104), 100, 10, self.state(), CFG)
        same = risk.review(self.make(stop=98.8, target=104), 100, 10, self.state(), stress)
        self.assertEqual(base.ok, same.ok)

    def test_good_setup_passes(self):
        d = risk.review(self.make(), 100, 10, self.state(), CFG)
        self.assertTrue(d.ok)
        self.assertGreater(d.size, 0)


class JournalAndMetrics(unittest.TestCase):
    def test_journal_roundtrip_keeps_rejected_with_hypothetical_result(self):
        df = frame([FLAT] * 12)
        with tempfile.TemporaryDirectory() as tmp:
            j = Journal(os.path.join(tmp, "j.db"))
            run = j.add_run("t", {}, CFG, {})
            res = run_backtest(df, [setup(df, 0, 95, 120), setup(df, 2, 95, 120)], CFG, journal=j, run_id=run)
            j.commit()
            rows = j.rows(run_id=run)
            self.assertEqual(len(rows), 2)
            rejected = [r for r in rows if r["decision"] == "ABGELEHNT"][0]
            self.assertIsNotNone(rejected["would_have_r"])
            self.assertEqual(len(j.aggregate()), 2)
            self.assertEqual(j.export_csv(os.path.join(tmp, "j.csv")), 2)
            self.assertIn("ABGELEHNT", j.to_markdown())
            self.assertEqual(len(res.trades), 1)

    def test_bootstrap_is_deterministic(self):
        rs = list(np.random.default_rng(3).normal(0.1, 1, 80))
        self.assertEqual(M.bootstrap_ci(rs, 300, seed=5), M.bootstrap_ci(rs, 300, seed=5))

    def test_verdict_needs_enough_trades(self):
        self.assertIn("Zu wenige", M.verdict(10, (0.5, 1.0)))
        self.assertIn("nicht von null", M.verdict(100, (-0.1, 0.2)))

    def test_r_from_prices_includes_fees(self):
        self.assertLess(r_from_prices(100, 110, 95, CFG), 2.0)


class DataAndStrategies(unittest.TestCase):
    def test_synthetic_is_deterministic_and_clean(self):
        a, b = D.synthetic(n=800, seed=1), D.synthetic(n=800, seed=1)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(D.check_quality(a), [])
        self.assertTrue(a.attrs["synthetic"])

    def test_quality_check_finds_gaps(self):
        df = D.synthetic(n=50, seed=2).drop(D.synthetic(n=50, seed=2).index[20:25])
        self.assertTrue(any("Lücken" in i for i in D.check_quality(df)))

    def test_signals_do_not_depend_on_the_future(self):
        df = D.synthetic(n=3000, seed=4)
        cut = 1800
        for name, cls in REGISTRY.items():
            full = {s.idx: s for s in cls().generate(df) if s.idx < cut}
            part = {s.idx: s for s in cls().generate(df.iloc[:cut])}
            self.assertEqual(sorted(full), sorted(part), name)
            for i in full:
                self.assertAlmostEqual(full[i].stop, part[i].stop, places=8)

    def test_fetch_pagination_with_fake_exchange(self):
        class Fake:
            rateLimit = 0

            def fetch_ohlcv(self, symbol, timeframe, since=None, limit=3):
                start = since or 0
                return [[t, 1, 2, 0.5, 1.5, 10] for t in range(start, min(start + limit, 10))]

        rows = D.fetch_ohlcv_all(Fake(), "X/Y", "1h", 0, limit=3, pause=0)
        self.assertEqual([r[0] for r in rows], list(range(10)))


if __name__ == "__main__":
    unittest.main()
