"""Trading journal: manual trades, CSV import with preview/mapping/duplicate detection, statistics."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import JournalImport, JournalTrade
from app.schemas import JournalTradeIn
from app.services.audit import audit
from quant.data.csv_import import parse_timestamp

FIELDS = [
    "symbol",
    "side",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "quantity",
    "fees",
    "realized_pnl",
    "setup",
    "tags",
    "notes",
    "market_type",
    "external_id",
]
REQUIRED = ["symbol", "side", "entry_time", "entry_price", "quantity"]
ALIASES = {
    "symbol": ["symbol", "pair", "market", "instrument", "ticker"],
    "side": ["side", "direction", "type", "position"],
    "entry_time": ["entry_time", "open_time", "opened", "entry date", "open date", "date", "time"],
    "exit_time": ["exit_time", "close_time", "closed", "exit date", "close date"],
    "entry_price": ["entry_price", "open_price", "entry", "avg entry price", "price"],
    "exit_price": ["exit_price", "close_price", "exit", "avg exit price"],
    "quantity": ["quantity", "qty", "size", "amount", "volume"],
    "fees": ["fees", "fee", "commission"],
    "realized_pnl": ["realized_pnl", "pnl", "profit", "realized pnl", "net pnl"],
    "setup": ["setup", "strategy"],
    "tags": ["tags", "labels"],
    "notes": ["notes", "note", "comment", "comments"],
    "market_type": ["market_type", "market type"],
    "external_id": ["external_id", "id", "trade id", "order id"],
}
SIDES = {"long": "long", "buy": "long", "l": "long", "short": "short", "sell": "short", "s": "short"}
SECRET_HINTS = ("api_key", "apikey", "secret", "passphrase", "private_key")


def dedupe_key(owner_id: str, symbol: str, side: str, entry_time: datetime, entry_price: float, quantity: float) -> str:
    t = entry_time.astimezone(UTC).isoformat(timespec="seconds")
    raw = f"{owner_id}|{symbol}|{side}|{t}|{entry_price:.10g}|{quantity:.10g}"
    return hashlib.sha256(raw.encode()).hexdigest()


def computed_pnl(t: JournalTrade) -> tuple[float | None, bool]:
    if t.realized_pnl is not None:
        return t.realized_pnl, False
    if t.exit_price is None:
        return None, False
    sign = 1 if t.side == "long" else -1
    return sign * (t.exit_price - t.entry_price) * t.quantity - t.fees, True


def to_out(t: JournalTrade) -> dict[str, Any]:
    pnl, computed = computed_pnl(t)
    d = {
        c: getattr(t, c)
        for c in (
            "id",
            "source_type",
            "external_id",
            "symbol",
            "market_type",
            "side",
            "entry_time",
            "exit_time",
            "entry_price",
            "exit_price",
            "quantity",
            "fees",
            "strategy_id",
            "setup",
            "tags",
            "notes",
            "emotions",
            "rule_compliance",
            "created_at",
        )
    }
    return {**d, "realized_pnl": pnl, "pnl_is_computed": computed}


def create_trade(
    db: Session,
    owner_id: str,
    data: JournalTradeIn,
    source_type: str = "manual",
    import_id: str | None = None,
    external_id: str | None = None,
) -> tuple[JournalTrade, bool]:
    if data.exit_time and data.exit_time < data.entry_time:
        raise ApiError(422, "invalid_trade", "Exit time is before entry time.")
    key = dedupe_key(owner_id, data.symbol, data.side, data.entry_time, data.entry_price, data.quantity)
    dup = (
        db.scalar(select(JournalTrade.id).where(JournalTrade.owner_id == owner_id, JournalTrade.dedupe_key == key))
        is not None
    )
    t = JournalTrade(
        owner_id=owner_id,
        source_type=source_type,
        import_id=import_id,
        external_id=external_id,
        dedupe_key=key,
        **data.model_dump(),
    )
    db.add(t)
    return t, dup


def _detect_mapping(headers: list[str]) -> dict[str, str]:
    lower = {h.strip().lower(): h for h in headers}
    mapping: dict[str, str] = {}
    for field, names in ALIASES.items():
        for n in names:
            if n in lower and lower[n] not in mapping.values():
                mapping[field] = lower[n]
                break
    return mapping


def _parse_dt(v: str) -> datetime:
    return datetime.fromtimestamp(parse_timestamp(v) / 1000, tz=UTC)


def parse_csv(db: Session, owner_id: str, content: str, mapping: dict[str, str] | None) -> dict[str, Any]:
    s = get_settings()
    if len(content.encode()) > s.max_csv_bytes:
        raise ApiError(413, "file_too_large", "File is too large.")
    reader = csv.DictReader(io.StringIO(content))
    headers = [h for h in (reader.fieldnames or []) if h]
    if not headers:
        raise ApiError(422, "invalid_csv", "CSV has no header row.")
    secret_cols = [h for h in headers if any(k in h.lower().replace(" ", "_") for k in SECRET_HINTS)]
    used = mapping or _detect_mapping(headers)
    unknown = [f for f in used if f not in FIELDS]
    if unknown:
        raise ApiError(422, "invalid_mapping", f"Unknown target fields: {', '.join(unknown)}.")
    missing_cols = [c for c in used.values() if c not in headers]
    if missing_cols:
        raise ApiError(422, "invalid_mapping", f"Columns not found in file: {', '.join(missing_cols)}.")
    missing = [f for f in REQUIRED if f not in used]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line, rec in enumerate(reader, start=2):
        if len(rows) >= s.max_journal_csv_rows:
            raise ApiError(413, "too_many_rows", f"Too many rows (limit {s.max_journal_csv_rows}).")
        out: dict[str, Any] = {"line": line, "errors": [], "duplicate": False, "data": None}
        if missing:
            out["errors"].append(f"Missing mapping for: {', '.join(missing)}")
            rows.append(out)
            continue
        raw = {f: (rec.get(col) or "").strip() for f, col in used.items()}
        try:
            data: dict[str, Any] = {
                "symbol": raw["symbol"].upper().replace("/", "").replace("-", ""),
                "side": SIDES.get(raw["side"].lower()),
                "entry_time": _parse_dt(raw["entry_time"]),
                "entry_price": float(raw["entry_price"]),
                "quantity": abs(float(raw["quantity"])),
            }
            if data["side"] is None:
                raise ValueError(f"unknown side '{raw['side']}'")
            if raw.get("exit_time"):
                data["exit_time"] = _parse_dt(raw["exit_time"])
            for f in ("exit_price", "fees", "realized_pnl"):
                if raw.get(f):
                    data[f] = float(raw[f])
            if raw.get("market_type") in ("spot", "futures"):
                data["market_type"] = raw["market_type"]
            for f in ("setup", "notes"):
                if raw.get(f):
                    data[f] = raw[f]
            if raw.get("tags"):
                data["tags"] = [t.strip()[:40] for t in raw["tags"].replace(";", ",").split(",") if t.strip()][:20]
            trade = JournalTradeIn.model_validate(data)
        except (ValueError, ValidationError) as exc:
            msg = (
                "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            out["errors"].append(msg[:300])
            rows.append(out)
            continue
        key = dedupe_key(owner_id, trade.symbol, trade.side, trade.entry_time, trade.entry_price, trade.quantity)
        out["duplicate"] = (
            key in seen
            or db.scalar(
                select(JournalTrade.id).where(JournalTrade.owner_id == owner_id, JournalTrade.dedupe_key == key)
            )
            is not None
        )
        seen.add(key)
        out["data"] = trade.model_dump(mode="json")
        out["external_id"] = raw.get("external_id") or None
        rows.append(out)
    return {
        "headers": headers,
        "mapping": used,
        "missing_required": missing,
        "secret_columns_ignored": secret_cols,
        "rows": rows,
        "valid": sum(1 for r in rows if not r["errors"]),
        "invalid": sum(1 for r in rows if r["errors"]),
        "duplicates": sum(1 for r in rows if r["duplicate"]),
    }


def commit_csv(
    db: Session, owner_id: str, filename: str, content: str, mapping: dict[str, str] | None, skip_duplicates: bool
) -> dict[str, Any]:
    preview = parse_csv(db, owner_id, content, mapping)
    if preview["missing_required"]:
        raise ApiError(
            422, "invalid_mapping", f"Map the required fields first: {', '.join(preview['missing_required'])}."
        )
    imp = JournalImport(
        owner_id=owner_id,
        filename=filename[:200],
        mapping=preview["mapping"],
        rows_total=len(preview["rows"]),
        rows_imported=0,
        rows_skipped=0,
        errors=[],
    )
    db.add(imp)
    db.flush()
    errors = []
    for r in preview["rows"]:
        if r["errors"]:
            errors.append({"line": r["line"], "errors": r["errors"]})
            imp.rows_skipped += 1
            continue
        if r["duplicate"] and skip_duplicates:
            imp.rows_skipped += 1
            continue
        create_trade(db, owner_id, JournalTradeIn.model_validate(r["data"]), "csv", imp.id, r.get("external_id"))
        imp.rows_imported += 1
    imp.errors = errors[:200]
    audit(
        db,
        owner_id,
        "journal.csv_imported",
        "journal_import",
        imp.id,
        {"imported": imp.rows_imported, "skipped": imp.rows_skipped},
    )
    return {"import_id": imp.id, "imported": imp.rows_imported, "skipped": imp.rows_skipped, "errors": imp.errors}


def stats(trades: list[JournalTrade]) -> dict[str, Any]:
    closed: list[float] = []
    incomplete = 0
    by_source: dict[str, int] = {}
    for t in trades:
        by_source[t.source_type] = by_source.get(t.source_type, 0) + 1
        pnl, _ = computed_pnl(t)
        if pnl is None:
            incomplete += 1
        else:
            closed.append(pnl)
    wins = [p for p in closed if p > 0]
    losses = [p for p in closed if p < 0]
    n = len(closed)
    return {
        "trades": len(trades),
        "closed_with_pnl": n,
        "open_or_incomplete": incomplete,
        "by_source": by_source,
        "net_pnl": sum(closed) if n else None,
        "win_rate": len(wins) / n if n else None,
        "profit_factor": (sum(wins) / -sum(losses)) if losses else None,
        "expectancy": sum(closed) / n if n else None,
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "note": "Statistics use closed trades with a known or computable PnL only. Mixed symbols and sources are summed as reported.",
    }
