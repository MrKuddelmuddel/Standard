"""Holt echte Kerzen von einer Börse (öffentliche Daten, kein API-Schlüssel nötig) und speichert sie als CSV.

Auf deinem Rechner:
    pip install ccxt
    python fetch_data.py --exchange binance --symbol BTC/USDT --timeframe 1h --since 2021-01-01 --out data/btc_1h.csv

Hinweis: In der Cloud-Umgebung, in der dieses Labor gebaut wurde, sind Börsen gesperrt. Die Abruf-Logik ist dort nur
mit einem Ersatzobjekt getestet worden, nicht gegen eine echte Börse.
"""
from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone

from lab.data import fetch_ohlcv_all


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--symbol", default="BTC/USDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--since", default="2021-01-01")
    ap.add_argument("--until")
    ap.add_argument("--out", default="data/btc_1h.csv")
    args = ap.parse_args()

    import ccxt  # erst hier importieren, damit der Rest ohne ccxt läuft

    ex = getattr(ccxt, args.exchange)({"enableRateLimit": True})
    to_ms = lambda s: int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)
    rows = fetch_ohlcv_all(ex, args.symbol, args.timeframe, to_ms(args.since), to_ms(args.until) if args.until else None)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        w.writerows(rows)
    print(f"{len(rows)} Kerzen gespeichert in {args.out}")


if __name__ == "__main__":
    main()
