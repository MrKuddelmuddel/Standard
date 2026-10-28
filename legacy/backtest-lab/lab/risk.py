"""TITAN, der Risiko-Wächter. Feste Regeln im Code, keine Meinung einer KI.

Jedes Setup wird geprüft. Besteht eine Regel nicht, wird es abgelehnt, und der Grund landet im Journal.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskState:
    equity: float
    day_start_equity: float
    in_position: bool
    last_exit_idx: int


@dataclass
class Decision:
    ok: bool
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    size: float = 0.0
    risk_amount: float = 0.0

    def reasons(self) -> list[str]:
        return [f"{name}: {msg}" for name, passed, msg in self.checks if not passed]


def review(setup, entry_price: float, idx: int, state: RiskState, cfg: dict) -> Decision:
    checks: list[tuple[str, bool, str]] = []
    stop_dist = entry_price - setup.stop

    checks.append(("Position", not state.in_position, "es ist schon eine Position offen" if state.in_position else "frei"))

    since_exit = idx - state.last_exit_idx
    cool_ok = since_exit >= cfg["cooldown_bars"]
    checks.append(("Abkühlphase", cool_ok, "zu kurz nach dem letzten Trade" if not cool_ok else "ok"))

    day_pnl = (state.equity - state.day_start_equity) / state.day_start_equity
    day_ok = day_pnl > -cfg["max_daily_loss"]
    checks.append(("Tageslimit", day_ok, f"Tagesverlust {day_pnl:.1%} erreicht das Limit" if not day_ok else "ok"))

    stop_ok = stop_dist > 0
    checks.append(("Stop gültig", stop_ok, "Stop liegt nicht unter dem Einstieg" if not stop_ok else "ok"))

    rr = (setup.target - entry_price) / stop_dist if stop_ok else 0.0
    rr_ok = rr >= cfg["min_rr"]
    checks.append(("Risk/Reward", rr_ok, f"{rr:.2f} liegt unter dem Minimum {cfg['min_rr']:.2f}" if not rr_ok else f"{rr:.2f}"))

    # Für den Kosten-Stresstest: Titan entscheidet mit den angenommenen Kosten, abgerechnet wird mit den gestressten.
    round_trip_cost = 2 * (cfg.get("decision_fee_rate", cfg["fee_rate"]) + cfg.get("decision_slippage_rate", cfg["slippage_rate"]))
    cost_ratio = round_trip_cost / (stop_dist / entry_price) if stop_ok else 9.99
    cost_ok = cost_ratio <= cfg["max_cost_ratio"]
    checks.append(("Kosten vs. Risiko", cost_ok, f"Kosten fressen {cost_ratio:.0%} des Risikos" if not cost_ok else f"{cost_ratio:.0%}"))

    size = risk_amount = 0.0
    if stop_ok:
        risk_amount = state.equity * cfg["risk_per_trade"]
        size = risk_amount / stop_dist
        cap = state.equity * cfg["max_position_pct"] / entry_price
        if size > cap:
            size = cap
            risk_amount = size * stop_dist
            checks.append(("Positionsgröße", True, "auf die Obergrenze begrenzt"))
        else:
            checks.append(("Positionsgröße", True, "nach 1-%-Regel berechnet"))
    ok = all(passed for _, passed, _ in checks)
    return Decision(ok=ok, checks=checks, size=size if ok else 0.0, risk_amount=risk_amount if ok else 0.0)
