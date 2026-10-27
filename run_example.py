"""Beispiel-Lauf: Training/Test-Aufteilung, Titan, Journal, Zufallsvergleich, Bericht.

Mit künstlichen Daten (nur zum Testen der Technik):
    python run_example.py --synthetic
Mit echten Daten (vorher fetch_data.py auf deinem Rechner ausführen):
    python run_example.py --csv data/btc_1h.csv
Journal ansehen:
    python run_example.py --journal
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

import numpy as np

from lab import data as D
from lab import metrics as M
from lab import report as R
from lab.backtest import random_baseline, run_backtest
from lab.journal import Journal
from lab.strategies import REGISTRY, param_grid


def choose_params(df, name, cfg, split):
    """Probiert alle Parametersätze auf dem Trainingsteil und wählt den mit dem besten Ø R (mindestens N Trades)."""
    rows = []
    for extra in param_grid(name):
        strat = REGISTRY[name](**extra)
        res = run_backtest(df, strat.generate(df), cfg, start_idx=cfg["warmup_bars"], end_idx=split)
        m = M.summarize(res.trades, res.equity, cfg["start_capital"])
        rows.append((m, strat.p))
    enough = [r for r in rows if r[0]["trades"] >= cfg["min_trades_for_choice"]]
    pool = enough or rows
    best = max(pool, key=lambda r: (r[0]["avg_r"] if r[0]["avg_r"] == r[0]["avg_r"] else -9e9))
    note = (f"Aus {len(rows)} Parametersätzen gewählt (Training). "
            + ("" if enough else "Kein Satz erreichte die Mindestzahl an Trades, Auswahl ist unsicher."))
    return best[1], len(rows), note


def doubled_costs(cfg):
    """Gleiche Entscheidungen wie im Basislauf, aber doppelte echte Kosten."""
    c = dict(cfg)
    c["decision_fee_rate"] = cfg["fee_rate"]
    c["decision_slippage_rate"] = cfg["slippage_rate"]
    c["fee_rate"] *= 2
    c["slippage_rate"] *= 2
    return c


def reject_reasons(rejected):
    """Zählt, woran Titan Setups abgelehnt hat, zum Beispiel 'Kosten vs. Risiko x12'."""
    counts = Counter()
    for r in rejected:
        for reason in json.loads(r["reasons"]):
            counts[reason.split(":")[0]] += 1
    return ", ".join(f"{k} ×{v}" for k, v in counts.most_common()) or "keine"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--journal", action="store_true", help="nur das Journal anzeigen")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    db_path = os.path.join(args.out, "journal.db")
    if args.journal:
        j = Journal(db_path)
        print(j.to_markdown(20))
        print()
        for a in j.aggregate():
            print(a)
        print("Getestete Parametersätze insgesamt:", j.total_trials())
        return

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    if args.csv:
        df = D.load_csv(args.csv)
    elif args.synthetic:
        df = D.synthetic(seed=args.seed, step_minutes=cfg["timeframe_minutes"])
    else:
        ap.error("Bitte --csv DATEI oder --synthetic angeben.")

    issues = D.check_quality(df, cfg["timeframe_minutes"])
    split = int(len(df) * (1 - cfg["oos_fraction"]))
    data_info = {"rows": len(df), "start": str(df.index[0])[:16], "end": str(df.index[-1])[:16], "synthetic": bool(df.attrs.get("synthetic")),
                 "split_note": f"Training bis {str(df.index[split - 1])[:10]}, Test danach"}

    if os.path.exists(db_path):
        os.remove(db_path)
    journal = Journal(db_path)
    sections = []
    for name in cfg["strategies"]:
        params, trials, note = choose_params(df, name, cfg, split)
        journal.add_trials(name, trials)
        strat = REGISTRY[name](**params)
        setups = strat.generate(df)

        run_is = journal.add_run(f"{name} Training", params, cfg, data_info)
        res_is = run_backtest(df, setups, cfg, journal, run_is, cfg["warmup_bars"], split, cfg["symbol"])
        run_oos = journal.add_run(f"{name} Test", params, cfg, data_info)
        res_oos = run_backtest(df, setups, cfg, journal, run_oos, split, len(df), cfg["symbol"])
        journal.commit()

        is_m = M.summarize(res_is.trades, res_is.equity, cfg["start_capital"])
        oos_m = M.summarize(res_oos.trades, res_oos.equity, cfg["start_capital"])
        rs = [t["r"] for t in res_oos.trades]
        ci = M.bootstrap_ci(rs, cfg["bootstrap_runs"])
        stress = run_backtest(df, setups, doubled_costs(cfg), start_idx=split, end_idx=len(df))
        stress_m = M.summarize(stress.trades, stress.equity, cfg["start_capital"])
        n_oos_setups = sum(1 for s in setups if s.idx >= split)
        base = random_baseline(df, cfg, strat.p, n_oos_setups, split, len(df), cfg["random_baseline_runs"])
        rej = [r["would_have_r"] for r in res_oos.rejected]
        sections.append(R.strategy_section(
            name, params, is_m, oos_m, ci, M.verdict(oos_m["trades"], ci), stress_m, base, oos_m["avg_r"],
            len(res_oos.trades), len(res_oos.rejected), float(np.mean(rej)) if rej else None,
            M.buy_and_hold(df, split, len(df), cfg), note, reject_reasons(res_oos.rejected)))

    text = R.full_report(data_info, cfg, issues, sections, journal.total_trials())
    path = os.path.join(args.out, "report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    csv_rows = journal.export_csv(os.path.join(args.out, "journal.csv"))
    print(text)
    print(f"Bericht: {path}  |  Journal: {db_path} ({csv_rows} Einträge, auch als journal.csv)")


if __name__ == "__main__":
    main()
