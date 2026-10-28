"""Parse OHLCV candles from CSV text with flexible timestamp formats (ms, s or ISO 8601, all UTC)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from .candles import CandleSeries, DataReport, build_series

TIME_COLUMNS = ("open_time", "timestamp", "time", "date")
MAX_ROWS = 500_000


class CsvFormatError(ValueError):
    pass


def parse_timestamp(value: str) -> int:
    v = value.strip()
    if not v:
        raise ValueError("empty timestamp")
    try:
        num = float(v)
    except ValueError:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
    return int(num) if num > 1e11 else int(num * 1000)


def parse_candles_csv(text: str, symbol: str, timeframe: str) -> tuple[CandleSeries, DataReport]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvFormatError("CSV has no header row.")
    fields = {f.strip().lower(): f for f in reader.fieldnames}
    tcol = next((fields[c] for c in TIME_COLUMNS if c in fields), None)
    if tcol is None:
        raise CsvFormatError(f"No time column found. Expected one of: {', '.join(TIME_COLUMNS)}.")
    missing = [c for c in ("open", "high", "low", "close", "volume") if c not in fields]
    if missing:
        raise CsvFormatError(f"Missing columns: {', '.join(missing)}.")
    rows: list[tuple[float, ...]] = []
    bad: list[dict] = []
    for line_no, rec in enumerate(reader, start=2):
        if len(rows) + len(bad) >= MAX_ROWS:
            raise CsvFormatError(f"Too many rows (limit {MAX_ROWS}).")
        try:
            t = parse_timestamp(rec[tcol])
            vals = tuple(float(rec[fields[c]]) for c in ("open", "high", "low", "close", "volume"))
        except (ValueError, TypeError) as exc:
            bad.append({"line": line_no, "reason": str(exc)})
            continue
        rows.append((t, *vals))
    series, report = build_series(rows, symbol, timeframe, source="csv")
    report.rows_in += len(bad)
    report.invalid_rows = [*bad, *report.invalid_rows]
    return series, report
