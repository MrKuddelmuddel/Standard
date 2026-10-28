"""Bar-by-bar execution model `next_open_v1`, shared by the backtest engine and paper trading.

Per bar i the simulator, in this order:
1. fills a pending order from bar i-1 at open[i] (adverse slippage, fee on notional),
2. checks stop loss / take profit inside bar i (stop wins if both are touched; gap through the stop fills at open),
3. schedules exits (exit signal, max bars) for open[i+1], or closes at close[i] on the last bar of the window,
4. schedules a new entry for open[i+1] when flat and an entry signal fired at the close of bar i,
5. marks equity to close[i].

All state is JSON-serializable so paper sessions can persist and resume it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..data.candles import CandleSeries
from ..strategy_schema.model import StrategyDefinition
from .signals import SignalSet


@dataclass
class SimState:
    realized: float
    position: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    trade_seq: int = 0
    bankrupt: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "realized": self.realized,
            "position": self.position,
            "pending": self.pending,
            "trade_seq": self.trade_seq,
            "bankrupt": self.bankrupt,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SimState:
        return cls(
            realized=float(d["realized"]),
            position=d.get("position"),
            pending=d.get("pending"),
            trade_seq=int(d.get("trade_seq", 0)),
            bankrupt=bool(d.get("bankrupt", False)),
        )


@dataclass
class BarOutput:
    index: int
    equity: float
    events: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)


class Simulator:
    def __init__(
        self,
        series: CandleSeries,
        defn: StrategyDefinition,
        signals: SignalSet,
        initial_capital: float,
        end_index: int,
        fee_bps: float | None = None,
        slippage_bps: float | None = None,
        state: SimState | None = None,
    ) -> None:
        self.s = series
        self.d = defn
        self.sig = signals
        self.end = end_index
        self.fee = (defn.costs.fee_bps if fee_bps is None else fee_bps) / 10_000
        self.slip = (defn.costs.slippage_bps if slippage_bps is None else slippage_bps) / 10_000
        self.state = state or SimState(realized=float(initial_capital))

    # ---------------------------------------------------------------- helpers
    def _ts(self, i: int) -> int:
        return int(self.s.open_time[i])

    def _equity_at(self, price: float) -> float:
        st = self.state
        pos = st.position
        if pos is None:
            return st.realized
        sign = 1 if pos["side"] == "long" else -1
        return st.realized + sign * pos["qty"] * (price - pos["entry_fill"])

    def _levels(self, side: str, fill: float, signal_index: int) -> tuple[float | None, float | None]:
        rm = self.d.risk_management
        sign = 1 if side == "long" else -1
        stop: float | None = None
        target: float | None = None
        sl, tp = rm.stop_loss, rm.take_profit
        if sl.type == "percent":
            stop = fill * (1 - sign * sl.value / 100)
        elif sl.type == "atr":
            a = float(self.sig.indicators[sl.atr_indicator or ""][signal_index])
            if math.isfinite(a) and a > 0:
                stop = fill - sign * sl.value * a
        if tp.type == "percent":
            target = fill * (1 + sign * tp.value / 100)
        elif tp.type == "atr":
            a = float(self.sig.indicators[tp.atr_indicator or ""][signal_index])
            if math.isfinite(a) and a > 0:
                target = fill + sign * tp.value * a
        elif tp.type == "r_multiple" and stop is not None:
            target = fill + sign * tp.value * abs(fill - stop)
        if stop is not None and (stop <= 0 or (side == "long" and stop >= fill) or (side == "short" and stop <= fill)):
            stop = None
        return stop, target

    def _size(self, fill: float, stop: float | None) -> tuple[float, str | None]:
        equity = self.state.realized
        if equity <= 0:
            return 0.0, "no capital left"
        ps = self.d.position_sizing
        max_notional = equity * ps.fraction / (1 + self.fee)
        if ps.type == "fixed_fraction":
            return max_notional / fill, None
        if stop is None:
            return 0.0, "risk_percent sizing needs a valid stop"
        risk_amount = equity * (ps.risk_percent or 0) / 100
        qty = risk_amount / abs(fill - stop)
        return min(qty, max_notional / fill), None

    # ---------------------------------------------------------------- order handling
    def _open(self, i: int, side: str, reason_index: int, out: BarOutput) -> None:
        st = self.state
        ref = float(self.s.open[i])
        sign = 1 if side == "long" else -1
        fill = ref * (1 + sign * self.slip)
        stop, target = self._levels(side, fill, reason_index)
        qty, problem = self._size(fill, stop)
        key = f"{self._ts(i)}:open_{side}"
        if qty <= 0 or not math.isfinite(qty):
            out.events.append(
                {
                    "type": "order_rejected",
                    "key": key,
                    "time": self._ts(i),
                    "side": side,
                    "reason": problem or "zero size",
                }
            )
            if problem == "no capital left":
                st.bankrupt = True
            return
        fee = qty * fill * self.fee
        st.realized -= fee
        st.trade_seq += 1
        st.position = {
            "seq": st.trade_seq,
            "side": side,
            "qty": qty,
            "entry_ref": ref,
            "entry_fill": fill,
            "entry_index": i,
            "entry_time": self._ts(i),
            "entry_fee": fee,
            "stop": stop,
            "target": target,
        }
        out.events.append(
            {
                "type": "order",
                "key": key,
                "time": self._ts(i),
                "side": "buy" if side == "long" else "sell",
                "intent": f"open_{side}",
                "order_type": "market",
                "qty": qty,
            }
        )
        out.events.append(
            {
                "type": "fill",
                "key": key,
                "time": self._ts(i),
                "price": fill,
                "ref_price": ref,
                "qty": qty,
                "fee": fee,
                "intent": f"open_{side}",
            }
        )

    def _close(self, i: int, ref: float, fill: float, reason: str, out: BarOutput) -> None:
        st = self.state
        pos = st.position
        assert pos is not None
        sign = 1 if pos["side"] == "long" else -1
        qty = pos["qty"]
        exit_fee = qty * fill * self.fee
        price_pnl = sign * qty * (fill - pos["entry_fill"])
        st.realized += price_pnl - exit_fee
        fees = pos["entry_fee"] + exit_fee
        slip_cost = qty * (abs(pos["entry_fill"] - pos["entry_ref"]) + abs(fill - ref))
        net = price_pnl - pos["entry_fee"] - exit_fee
        risk = qty * abs(pos["entry_fill"] - pos["stop"]) if pos.get("stop") is not None else None
        trade = {
            "sequence": pos["seq"],
            "side": pos["side"],
            "entry_time": pos["entry_time"],
            "exit_time": self._ts(i),
            "entry_index": pos["entry_index"],
            "exit_index": i,
            "bars_held": i - pos["entry_index"] + 1,
            "entry_price": pos["entry_fill"],
            "exit_price": fill,
            "quantity": qty,
            "gross_pnl": net + fees + slip_cost,
            "fees": fees,
            "slippage_cost": slip_cost,
            "funding_cost": None,
            "net_pnl": net,
            "exit_reason": reason,
            "stop": pos.get("stop"),
            "target": pos.get("target"),
            "r_multiple": (net / risk) if risk else None,
            "return_pct": net / (qty * pos["entry_fill"]),
        }
        key = f"{self._ts(i)}:close_{pos['side']}"
        out.events.append(
            {
                "type": "order",
                "key": key,
                "time": self._ts(i),
                "side": "sell" if sign == 1 else "buy",
                "intent": f"close_{pos['side']}",
                "order_type": "stop"
                if reason.startswith("stop")
                else ("limit" if reason == "take_profit" else "market"),
                "qty": qty,
                "reason": reason,
            }
        )
        out.events.append(
            {
                "type": "fill",
                "key": key,
                "time": self._ts(i),
                "price": fill,
                "ref_price": ref,
                "qty": qty,
                "fee": exit_fee,
                "intent": f"close_{pos['side']}",
            }
        )
        out.trades.append(trade)
        st.position = None

    def _intrabar(self, i: int, out: BarOutput) -> None:
        pos = self.state.position
        if pos is None:
            return
        o, h, low = float(self.s.open[i]), float(self.s.high[i]), float(self.s.low[i])
        stop, target, long = pos.get("stop"), pos.get("target"), pos["side"] == "long"
        after_entry = i > pos["entry_index"]
        if stop is not None:
            if after_entry and ((long and o <= stop) or (not long and o >= stop)):
                self._close(i, o, o * (1 - self.slip) if long else o * (1 + self.slip), "stop_gap", out)
                return
            if (long and low <= stop) or (not long and h >= stop):
                self._close(i, stop, stop * (1 - self.slip) if long else stop * (1 + self.slip), "stop_loss", out)
                return
        if target is not None and ((long and h >= target) or (not long and low <= target)):
            self._close(i, target, target, "take_profit", out)

    # ---------------------------------------------------------------- main step
    def process_bar(self, i: int) -> BarOutput:
        st = self.state
        out = BarOutput(index=i, equity=0.0)
        if st.pending is not None:
            pend, st.pending = st.pending, None
            if pend["action"] == "close" and st.position is not None:
                ref = float(self.s.open[i])
                fill = ref * (1 - self.slip) if st.position["side"] == "long" else ref * (1 + self.slip)
                self._close(i, ref, fill, pend["reason"], out)
            elif pend["action"] in ("open_long", "open_short") and st.position is None and not st.bankrupt:
                self._open(i, pend["action"].removeprefix("open_"), pend["signal_index"], out)
        self._intrabar(i, out)
        last = i >= self.end - 1
        held = st.position
        if held is not None:
            side = held["side"]
            if last:
                ref = float(self.s.close[i])
                fill = ref * (1 - self.slip) if side == "long" else ref * (1 + self.slip)
                self._close(i, ref, fill, "end_of_period", out)
            else:
                mb = self.d.risk_management.max_bars_in_trade
                exit_sig = self.sig.exit_long[i] if side == "long" else self.sig.exit_short[i]
                if exit_sig:
                    st.pending = {"action": "close", "reason": "exit_signal", "signal_index": i}
                elif mb is not None and i - held["entry_index"] + 1 >= mb:
                    st.pending = {"action": "close", "reason": "max_bars", "signal_index": i}
        if st.position is None and st.pending is None and not last and not st.bankrupt:
            go_long = bool(self.sig.entry_long[i])
            go_short = bool(self.sig.entry_short[i])
            if go_long and go_short:
                out.events.append({"type": "signal_conflict", "key": f"{self._ts(i)}:conflict", "time": self._ts(i)})
            elif go_long or go_short:
                side = "long" if go_long else "short"
                st.pending = {"action": f"open_{side}", "reason": "entry_signal", "signal_index": i}
                out.events.append(
                    {"type": "signal", "key": f"{self._ts(i)}:signal_{side}", "time": self._ts(i), "side": side}
                )
        out.equity = self._equity_at(float(self.s.close[i]))
        return out


def equity_drawdown(equity: np.ndarray) -> np.ndarray:
    if len(equity) == 0:
        return equity
    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, equity / peak - 1.0, 0.0)
    return dd
