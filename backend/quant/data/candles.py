"""OHLCV candle series in UTC with validation, de-duplication and a reproducible fingerprint."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

TIMEFRAME_MS: dict[str, int] = {
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


@dataclass(frozen=True)
class CandleSeries:
    """Candles sorted by open time (milliseconds since epoch, UTC). Arrays are read-only."""

    symbol: str
    timeframe: str
    open_time: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    synthetic: bool = False
    source: str = "unknown"

    def __post_init__(self) -> None:
        n = len(self.open_time)
        for name in ("open", "high", "low", "close", "volume"):
            arr = getattr(self, name)
            if len(arr) != n:
                raise ValueError(f"Array '{name}' has length {len(arr)}, expected {n}.")
            arr.setflags(write=False)
        self.open_time.setflags(write=False)

    def __len__(self) -> int:
        return len(self.open_time)

    @property
    def bar_ms(self) -> int:
        return TIMEFRAME_MS[self.timeframe]

    def fingerprint(self) -> str:
        """SHA-256 over symbol, timeframe and every OHLCV value. Identical data gives an identical fingerprint."""
        h = hashlib.sha256()
        h.update(f"{self.symbol}|{self.timeframe}|{len(self)}|".encode())
        h.update(self.open_time.astype("<i8").tobytes())
        for arr in (self.open, self.high, self.low, self.close, self.volume):
            h.update(arr.astype("<f8").tobytes())
        return h.hexdigest()


@dataclass
class DataReport:
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    invalid_rows: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    misaligned: int = 0

    @property
    def ok(self) -> bool:
        return not self.invalid_rows

    def to_dict(self) -> dict:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duplicates_removed": self.duplicates_removed,
            "invalid_rows": self.invalid_rows[:50],
            "invalid_count": len(self.invalid_rows),
            "gaps": self.gaps[:50],
            "gap_count": len(self.gaps),
            "misaligned": self.misaligned,
        }


def _row_problem(o: float, h: float, low: float, c: float, v: float) -> str | None:
    vals = (o, h, low, c, v)
    if any(not np.isfinite(x) for x in vals):
        return "non-finite value"
    if min(o, h, low, c) <= 0:
        return "price must be positive"
    if v < 0:
        return "negative volume"
    if h < max(o, c) or low > min(o, c) or h < low:
        return "high/low inconsistent with open/close"
    return None


def build_series(
    rows: Iterable[Sequence[float]],
    symbol: str,
    timeframe: str,
    *,
    synthetic: bool = False,
    source: str = "unknown",
) -> tuple[CandleSeries, DataReport]:
    """Build a series from rows (open_time_ms, open, high, low, close, volume).

    Rows are sorted, exact duplicates by open time are removed (first one wins) and invalid rows are
    dropped and reported. Nothing is silently repaired.
    """
    if timeframe not in TIMEFRAME_MS:
        raise ValueError(f"Unsupported timeframe '{timeframe}'.")
    report = DataReport()
    parsed: dict[int, tuple[float, float, float, float, float]] = {}
    for raw in rows:
        report.rows_in += 1
        t = int(raw[0])
        o, h, low, c, v = (float(x) for x in raw[1:6])
        problem = _row_problem(o, h, low, c, v)
        if problem:
            report.invalid_rows.append({"open_time": t, "reason": problem})
            continue
        if t in parsed:
            report.duplicates_removed += 1
            continue
        parsed[t] = (o, h, low, c, v)
    times = sorted(parsed)
    data = np.array([parsed[t] for t in times], dtype=float).reshape(-1, 5)
    series = CandleSeries(
        symbol=symbol,
        timeframe=timeframe,
        open_time=np.array(times, dtype=np.int64),
        open=data[:, 0].copy(),
        high=data[:, 1].copy(),
        low=data[:, 2].copy(),
        close=data[:, 3].copy(),
        volume=data[:, 4].copy(),
        synthetic=synthetic,
        source=source,
    )
    report.rows_out = len(series)
    gaps, misaligned = validate_series(series)
    report.gaps = gaps
    report.misaligned = misaligned
    return series, report


def validate_series(series: CandleSeries) -> tuple[list[dict], int]:
    """Return (gaps, misaligned_count). A gap is a jump larger than one bar between consecutive candles."""
    step = series.bar_ms
    t = series.open_time
    gaps: list[dict] = []
    if len(t) > 1:
        diffs = np.diff(t)
        for i in np.flatnonzero(diffs != step):
            if diffs[i] > step:
                gaps.append({"after": int(t[i]), "before": int(t[i + 1]), "missing_bars": int(diffs[i] // step - 1)})
    misaligned = int(np.count_nonzero(t % step)) if step < TIMEFRAME_MS["1d"] else 0
    return gaps, misaligned
