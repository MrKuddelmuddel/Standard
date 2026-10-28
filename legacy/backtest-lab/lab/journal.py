"""Das Journal: hält jedes Setup fest, auch die abgelehnten, samt Ausgang und, bei Ablehnung, dem Ergebnis, das es gehabt hätte.

So siehst du später ehrlich, ob der Risiko-Wächter Verluste verhindert oder gute Chancen blockiert.
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime, timezone

SETUP_COLUMNS = ["run_id", "ts", "symbol", "strategy", "side", "entry", "stop", "target", "rr", "decision", "reasons", "size",
                 "risk_amount", "exit_ts", "exit_price", "exit_reason", "bars_held", "pnl", "fees", "r_multiple", "would_have_r", "notes"]


class Journal:
    def __init__(self, path: str):
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, label TEXT, params TEXT, config TEXT, data_info TEXT);
        CREATE TABLE IF NOT EXISTS trials (id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, strategy TEXT, count INTEGER);
        CREATE TABLE IF NOT EXISTS setups (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, ts TEXT, symbol TEXT, strategy TEXT, side TEXT,
            entry REAL, stop REAL, target REAL, rr REAL, decision TEXT, reasons TEXT, size REAL, risk_amount REAL, exit_ts TEXT,
            exit_price REAL, exit_reason TEXT, bars_held INTEGER, pnl REAL, fees REAL, r_multiple REAL, would_have_r REAL, notes TEXT);
        """)

    def add_run(self, label: str, params: dict, cfg: dict, data_info: dict) -> int:
        cur = self.con.execute("INSERT INTO runs (created, label, params, config, data_info) VALUES (?,?,?,?,?)",
                               (datetime.now(timezone.utc).isoformat(), label, json.dumps(params), json.dumps(cfg), json.dumps(data_info)))
        self.con.commit()
        return int(cur.lastrowid)

    def add_trials(self, strategy: str, count: int) -> None:
        self.con.execute("INSERT INTO trials (created, strategy, count) VALUES (?,?,?)", (datetime.now(timezone.utc).isoformat(), strategy, count))
        self.con.commit()

    def total_trials(self) -> int:
        row = self.con.execute("SELECT COALESCE(SUM(count),0) AS n FROM trials").fetchone()
        return int(row["n"])

    def add_setup(self, run_id: int | None, row: dict) -> None:
        values = [run_id] + [row.get(k) for k in SETUP_COLUMNS[1:]]
        self.con.execute(f"INSERT INTO setups ({','.join(SETUP_COLUMNS)}) VALUES ({','.join('?' * len(SETUP_COLUMNS))})", values)

    def commit(self) -> None:
        self.con.commit()

    def rows(self, run_id: int | None = None, decision: str | None = None, limit: int | None = None) -> list[dict]:
        sql, args = "SELECT * FROM setups WHERE 1=1", []
        if run_id is not None:
            sql += " AND run_id=?"
            args.append(run_id)
        if decision is not None:
            sql += " AND decision=?"
            args.append(decision)
        sql += " ORDER BY id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def runs(self) -> list[dict]:
        return [dict(r) for r in self.con.execute("SELECT * FROM runs ORDER BY id").fetchall()]

    def export_csv(self, path: str) -> int:
        rows = self.rows()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id"] + SETUP_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        return len(rows)

    def aggregate(self) -> list[dict]:
        """Je Lauf und Entscheidung: Anzahl, Trefferquote und Ø R (bei Ablehnungen das hypothetische Ergebnis)."""
        out = []
        for run in self.runs():
            for decision in ("TRADE", "ABGELEHNT"):
                rows = self.rows(run_id=run["id"], decision=decision)
                key = "r_multiple" if decision == "TRADE" else "would_have_r"
                rs = [r[key] for r in rows if r[key] is not None]
                if not rows:
                    continue
                out.append({"lauf": run["label"], "entscheidung": decision, "anzahl": len(rows), "mit_ergebnis": len(rs),
                            "trefferquote": (sum(1 for x in rs if x > 0) / len(rs)) if rs else None,
                            "durchschnitt_r": (sum(rs) / len(rs)) if rs else None})
        return out

    def to_markdown(self, limit: int = 15) -> str:
        lines = ["| Zeit | Strategie | Entscheidung | Einstieg | Stop | Ziel | Ausgang | R | Grund |", "|---|---|---|---|---|---|---|---|---|"]
        for r in self.rows(limit=limit):
            rr = r["r_multiple"] if r["decision"] == "TRADE" else r["would_have_r"]
            tag = "" if rr is None else (f"{rr:+.2f}" if r["decision"] == "TRADE" else f"({rr:+.2f})")
            reasons = "; ".join(json.loads(r["reasons"] or "[]"))
            lines.append(f"| {r['ts'][:16]} | {r['strategy']} | {r['decision']} | {r['entry']:.0f} | {r['stop']:.0f} | {r['target']:.0f} | "
                         f"{r['exit_reason'] or ''} | {tag} | {reasons} |")
        return "\n".join(lines)
