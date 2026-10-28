"""Baut den Bericht als Text (Markdown). Der Bericht nennt Schwächen genauso deutlich wie Stärken."""
from __future__ import annotations

import json

import numpy as np


def pct(x: float) -> str:
    return "–" if x != x else f"{x:.1%}".replace(".", ",")


def num(x: float, digits: int = 2) -> str:
    if x != x:
        return "–"
    if x == float("inf"):
        return "∞"
    return f"{x:.{digits}f}".replace(".", ",")


def metrics_row(label: str, m: dict) -> str:
    return (f"| {label} | {m['trades']} | {pct(m['win_rate'])} | {num(m['avg_r'])} | {num(m['profit_factor'])} | "
            f"{pct(m['return_pct'])} | {pct(m['max_dd'])} |")


def strategy_section(name: str, params: dict, is_m: dict, oos_m: dict, ci: tuple[float, float], verdict_text: str,
                     stress_m: dict, baseline: np.ndarray, oos_avg_r: float, accepted: int, rejected: int,
                     rej_avg_r: float | None, bh: float, grid_best_note: str, reject_note: str = "") -> str:
    lines = [f"## Strategie `{name}`", "", f"Gewählte Parameter (auf dem Trainingsteil bestimmt): `{json.dumps(params)}`", "",
             grid_best_note, "",
             "| Zeitraum | Trades | Trefferquote | Ø R | Profit-Faktor | Rendite | Max. Verlust vom Hoch |",
             "|---|---|---|---|---|---|---|",
             metrics_row("Training (bekannt)", is_m), metrics_row("Test (ungesehen)", oos_m), "",
             f"- **95-%-Spanne für Ø R im Test:** {num(ci[0])} bis {num(ci[1])}. {verdict_text}",
             f"- **Kosten-Stress (doppelte Gebühren und Slippage):** Ø R im Test {num(stress_m['avg_r'])}, Rendite {pct(stress_m['return_pct'])}."]
    if len(baseline):
        better = float((baseline < oos_avg_r).mean()) if oos_avg_r == oos_avg_r else float("nan")
        lines.append(f"- **Zufallsvergleich ({len(baseline)} Läufe mit zufälligen Einstiegen, gleiche Regeln):** "
                     f"Die Strategie liegt besser als {pct(better)} der Zufallsläufe (Ø R der Zufallsläufe: {num(float(baseline.mean()))}).")
    lines.append(f"- **Titan im Test:** {accepted} Setups angenommen, {rejected} abgelehnt. "
                 + ("Ø R der abgelehnten, wenn man sie trotzdem gehandelt hätte: " + num(rej_avg_r) + "." if rej_avg_r is not None else "Keine bewertbaren Ablehnungen."))
    if reject_note:
        lines.append(f"- **Gründe der Ablehnungen (Mehrfachnennung möglich):** {reject_note}.")
    lines.append(f"- **Zum Vergleich Buy & Hold im Testzeitraum:** {pct(bh)}.")
    lines.append("")
    return "\n".join(lines)


def full_report(data_info: dict, cfg: dict, issues: list[str], sections: list[str], trials: int) -> str:
    head = ["# Backtest-Bericht", ""]
    if data_info.get("synthetic"):
        head += ["> **Achtung: künstliche Zufallsdaten.** Die Zahlen unten zeigen nur, dass die Technik läuft. "
                 "Sie sagen nichts über echte Märkte. Mit Zufallsdaten darf es keinen verlässlichen Vorteil geben.", ""]
    head += [f"- Daten: {data_info['rows']} Kerzen, {data_info['start']} bis {data_info['end']}, "
             f"{data_info['split_note']}",
             f"- Kosten: Gebühr {cfg['fee_rate']:.2%} je Seite, Slippage {cfg['slippage_rate']:.2%}. ".replace(".", ",") +
             f"Risiko je Trade {cfg['risk_per_trade']:.0%}, Tageslimit {cfg['max_daily_loss']:.0%}, Start {cfg['start_capital']:.0f} (Spielgeld)."]
    if issues:
        head += ["- Datenprüfung: " + " ".join(issues)]
    else:
        head += ["- Datenprüfung: keine Auffälligkeiten."]
    head += [f"- Getestete Parametersätze insgesamt: {trials}. Je mehr man ausprobiert, desto eher findet man einen Zufallstreffer. "
             "Zähle deshalb alle Versuche mit.", ""]
    tail = ["## So liest du das", "",
            "- **R** ist das Ergebnis in Vielfachen des Risikos bis zum Stop. +1 R heißt: so viel gewonnen, wie du bis zum Stop riskiert hättest.",
            "- **Training** ist der Zeitraum, auf dem Parameter ausgesucht wurden. **Test** ist ungesehen. Zählt nur der Test.",
            "- Ein gutes Trainingsergebnis mit schwachem Testergebnis ist der Normalfall bei Überanpassung.",
            "- Erst wenn Test, Kosten-Stress und Zufallsvergleich zusammen überzeugen, lohnt sich der nächste Schritt (Paper-Forward-Test).", ""]
    return "\n".join(head + sections + tail)
