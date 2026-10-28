"""Market data sources: CSV import, synthetic demo data, provider fetch, loading series for the engine.

Imports are idempotent: candles are keyed by (source, open_time). Every change bumps the source revision and
recomputes the dataset fingerprint, so a backtest can always be tied to the exact data it used.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.models import Candle, MarketDataSource
from app.services.audit import audit
from quant.data.candles import TIMEFRAME_MS, CandleSeries, DataReport, build_series
from quant.data.csv_import import CsvFormatError, parse_candles_csv
from quant.data.providers.base import ProviderError
from quant.data.providers.binance import BinanceSpotProvider
from quant.data.synthetic import generate

CHUNK = 5_000


def visible_sources(owner_id: str):
    return select(MarketDataSource).where(
        or_(MarketDataSource.owner_id == owner_id, MarketDataSource.owner_id.is_(None))
    )


def get_source(db: Session, source_id: str, owner_id: str) -> MarketDataSource:
    src = db.get(MarketDataSource, source_id)
    if src is None or (src.owner_id is not None and src.owner_id != owner_id):
        raise not_found("Market data source")
    return src


def _get_or_create(
    db: Session, owner_id: str | None, provider: str, symbol: str, timeframe: str, **fields: Any
) -> MarketDataSource:
    src = db.scalar(
        select(MarketDataSource).where(
            MarketDataSource.owner_id == owner_id if owner_id else MarketDataSource.owner_id.is_(None),
            MarketDataSource.provider == provider,
            MarketDataSource.symbol == symbol,
            MarketDataSource.timeframe == timeframe,
        )
    )
    if src is None:
        src = MarketDataSource(owner_id=owner_id, provider=provider, symbol=symbol, timeframe=timeframe, **fields)
        db.add(src)
        db.flush()
    return src


def _store(
    db: Session, src: MarketDataSource, series: CandleSeries, report: DataReport, replace: bool
) -> dict[str, Any]:
    if len(series) > get_settings().max_csv_rows:
        raise ApiError(413, "too_many_rows", f"Too many candles ({len(series)}). Limit: {get_settings().max_csv_rows}.")
    src.revision += 1
    if replace:
        db.execute(delete(Candle).where(Candle.source_id == src.id))
        existing: set[int] = set()
    else:
        existing = set(db.scalars(select(Candle.open_time).where(Candle.source_id == src.id)))
    step = TIMEFRAME_MS[series.timeframe]
    new_rows = [
        {
            "source_id": src.id,
            "open_time": int(t),
            "close_time": int(t) + step - 1,
            "open": float(o),
            "high": float(h),
            "low": float(lo),
            "close": float(c),
            "volume": float(v),
            "revision": src.revision,
        }
        for t, o, h, lo, c, v in zip(
            series.open_time, series.open, series.high, series.low, series.close, series.volume, strict=True
        )
        if int(t) not in existing
    ]
    for k in range(0, len(new_rows), CHUNK):
        db.execute(insert(Candle), new_rows[k : k + CHUNK])
    db.flush()
    loaded = load_series(db, src)
    src.row_count = len(loaded)
    src.fingerprint = loaded.fingerprint() if len(loaded) else None
    src.first_time = int(loaded.open_time[0]) if len(loaded) else None
    src.last_time = int(loaded.open_time[-1]) if len(loaded) else None
    from quant.data.candles import validate_series

    gaps, _ = validate_series(loaded)
    src.meta = {
        **(src.meta or {}),
        "last_import": {**report.to_dict(), "inserted": len(new_rows), "skipped_existing": len(series) - len(new_rows)},
        "gap_count": len(gaps),
        "gaps": gaps[:20],
    }
    src.status = "ready"
    return src.meta["last_import"]


def import_csv(
    db: Session, owner_id: str, symbol: str, timeframe: str, text: str
) -> tuple[MarketDataSource, dict[str, Any]]:
    if len(text.encode()) > get_settings().max_csv_bytes:
        raise ApiError(413, "file_too_large", f"File is larger than {get_settings().max_csv_bytes // 1_000_000} MB.")
    try:
        series, report = parse_candles_csv(text, symbol, timeframe)
    except CsvFormatError as exc:
        raise ApiError(422, "invalid_csv", str(exc)) from exc
    if len(series) == 0:
        raise ApiError(422, "invalid_csv", "No valid candles found.", report.to_dict())
    src = _get_or_create(db, owner_id, "csv", symbol, timeframe, exchange="user_upload", market_type="spot")
    summary = _store(db, src, series, report, replace=False)
    audit(db, owner_id, "market_data.csv_imported", "market_data_source", src.id, {"rows": len(series)})
    return src, summary


def create_demo(db: Session, owner_id: str, symbol: str, timeframe: str, bars: int, seed: int) -> MarketDataSource:
    series = generate(symbol, timeframe, bars, seed)
    src = _get_or_create(
        db, owner_id, "synthetic", symbol, timeframe, exchange="demo", market_type="spot", is_synthetic=True
    )
    src.meta = {"seed": seed, "note": "Synthetic random data for demos. Not real market data."}
    _store(db, src, series, DataReport(rows_in=len(series), rows_out=len(series)), replace=True)
    audit(db, owner_id, "market_data.demo_generated", "market_data_source", src.id, {"bars": bars, "seed": seed})
    return src


def fetch_provider(
    db: Session,
    owner_id: str,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    provider: BinanceSpotProvider | None = None,
) -> tuple[MarketDataSource, dict[str, Any]]:
    if end_ms <= start_ms:
        raise ApiError(422, "invalid_range", "End must be after start.")
    bars = (end_ms - start_ms) // TIMEFRAME_MS[timeframe]
    if bars > get_settings().max_csv_rows:
        raise ApiError(413, "range_too_large", f"Range covers {bars} candles. Limit: {get_settings().max_csv_rows}.")
    s = get_settings()
    p = provider or BinanceSpotProvider(base_url=s.binance_base_url, timeout=s.market_data_timeout_seconds)
    try:
        rows = p.fetch_historical_candles(symbol, timeframe, start_ms, end_ms)
    except ProviderError as exc:
        raise ApiError(502, "provider_error", f"Market data provider failed: {exc}") from exc
    series, report = build_series(rows, symbol, timeframe, source=p.name)
    if len(series) == 0:
        raise ApiError(422, "no_data", "The provider returned no candles for this range.")
    src = _get_or_create(db, owner_id, p.name, symbol, timeframe, exchange="binance", market_type="spot")
    summary = _store(db, src, series, report, replace=False)
    audit(db, owner_id, "market_data.fetched", "market_data_source", src.id, {"rows": len(series), "provider": p.name})
    return src, summary


def load_series(
    db: Session, src: MarketDataSource, start_ms: int | None = None, end_ms: int | None = None
) -> CandleSeries:
    stmt = select(Candle.open_time, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume).where(
        Candle.source_id == src.id
    )
    if start_ms is not None:
        stmt = stmt.where(Candle.open_time >= start_ms)
    if end_ms is not None:
        stmt = stmt.where(Candle.open_time <= end_ms)
    rows = db.execute(stmt.order_by(Candle.open_time)).all()
    arr = np.array(rows, dtype=float).reshape(-1, 6)
    return CandleSeries(
        symbol=src.symbol,
        timeframe=src.timeframe,
        open_time=arr[:, 0].astype(np.int64),
        open=arr[:, 1].copy(),
        high=arr[:, 2].copy(),
        low=arr[:, 3].copy(),
        close=arr[:, 4].copy(),
        volume=arr[:, 5].copy(),
        synthetic=src.is_synthetic,
        source=src.provider,
    )


def candle_preview(db: Session, src: MarketDataSource, limit: int = 300) -> list[list[float]]:
    rows = db.execute(
        select(Candle.open_time, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
        .where(Candle.source_id == src.id)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    ).all()
    return [list(r) for r in reversed(rows)]


def count_sources(db: Session, owner_id: str) -> int:
    return int(db.scalar(select(func.count()).select_from(visible_sources(owner_id).subquery())) or 0)
