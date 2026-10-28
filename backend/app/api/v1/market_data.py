from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models import User
from app.schemas import DemoDataRequest, FetchDataRequest, SourceOut
from app.services import market_data as svc

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/sources", response_model=list[SourceOut])
def sources(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list:
    return list(db.scalars(svc.visible_sources(user.id).order_by(svc.MarketDataSource.created_at.desc())))


@router.get("/sources/{source_id}", response_model=SourceOut)
def source(source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.get_source(db, source_id, user.id)


@router.get("/sources/{source_id}/candles")
def candles(
    source_id: str, limit: int = 300, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    src = svc.get_source(db, source_id, user.id)
    return {
        "source_id": src.id,
        "is_synthetic": src.is_synthetic,
        "columns": ["open_time", "open", "high", "low", "close", "volume"],
        "rows": svc.candle_preview(db, src, max(10, min(limit, 1000))),
    }


@router.post("/demo", response_model=SourceOut, status_code=201)
def demo(body: DemoDataRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    src = svc.create_demo(db, user.id, body.symbol, body.timeframe, body.bars, body.seed)
    db.commit()
    return src


@router.post("/import-csv", status_code=201)
async def import_csv(
    request: Request,
    symbol: str = Form(..., pattern="^(BTCUSDT|ETHUSDT)$"),
    timeframe: str = Form(..., pattern="^(15m|1h|4h|1d)$"),
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    raw = await file.read(get_settings().max_csv_bytes + 1)
    if len(raw) > get_settings().max_csv_bytes:
        raise ApiError(413, "file_too_large", "File is too large.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_encoding", "File must be UTF-8 encoded CSV.") from exc
    src, summary = svc.import_csv(db, user.id, symbol, timeframe, text)
    db.commit()
    return {"source": SourceOut.model_validate(src).model_dump(mode="json"), "import": summary}


@router.post("/fetch", status_code=201)
def fetch(body: FetchDataRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    limiter.check(f"expensive:{user.id}", get_settings().expensive_requests_per_minute)
    src, summary = svc.fetch_provider(
        db, user.id, body.symbol, body.timeframe, int(body.start.timestamp() * 1000), int(body.end.timestamp() * 1000)
    )
    db.commit()
    return {"source": SourceOut.model_validate(src).model_dump(mode="json"), "import": summary}


@router.get("/providers")
def providers(_: User = Depends(current_user)) -> dict:
    return {
        "providers": [
            {
                "id": "binance_spot",
                "name": "Binance Spot (public klines)",
                "requires_key": False,
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "note": "Needs outbound network access to api.binance.com; may be geo-restricted. Check the provider's terms.",
            },
            {
                "id": "csv",
                "name": "CSV upload",
                "requires_key": False,
                "note": "Columns: timestamp/open_time, open, high, low, close, volume (UTC).",
            },
            {
                "id": "synthetic",
                "name": "Synthetic demo data",
                "requires_key": False,
                "note": "Random data, clearly marked. Not real market data.",
            },
        ]
    }
