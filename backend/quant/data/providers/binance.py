"""Binance Spot public market data adapter (klines). No API key needed.

Endpoint: GET {base}/api/v3/klines with symbol, interval, startTime, endTime, limit (max 1000).
Each kline is [open_time, open, high, low, close, volume, close_time, ...] with prices as strings.
Access can be geo-restricted; check Binance's terms before commercial use.
"""

from __future__ import annotations

import time

import httpx

from .base import MarketDataProvider, ProviderError, ProviderHealth

INTERVALS = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
RETRY_STATUS = {429, 418, 500, 502, 503, 504}


class BinanceSpotProvider(MarketDataProvider):
    name = "binance_spot"

    def __init__(
        self,
        base_url: str = "https://api.binance.com",
        client: httpx.Client | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        page_limit: int = 1000,
        sleep=time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=timeout)
        self.max_retries = max_retries
        self.page_limit = page_limit
        self.sleep = sleep

    def _get(self, path: str, params: dict) -> list:
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.get(f"{self.base_url}{path}", params=params)
            except httpx.TimeoutException as exc:
                if attempt == self.max_retries:
                    raise ProviderError("Binance did not answer in time.") from exc
                self.sleep(delay)
                delay *= 2
                continue
            except httpx.HTTPError as exc:
                raise ProviderError(f"Network error while contacting Binance: {type(exc).__name__}.") from exc
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, list):
                    raise ProviderError("Unexpected response format from Binance.")
                return data
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                retry_after = resp.headers.get("Retry-After")
                self.sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
                delay *= 2
                continue
            raise ProviderError(f"Binance returned HTTP {resp.status_code}.")
        raise ProviderError("Binance request failed after retries.")

    def fetch_historical_candles(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> list[list[float]]:
        if symbol not in SYMBOLS:
            raise ProviderError(f"Symbol {symbol} is not supported.")
        if timeframe not in INTERVALS:
            raise ProviderError(f"Timeframe {timeframe} is not supported.")
        rows: list[list[float]] = []
        cursor = start_ms
        while cursor <= end_ms:
            batch = self._get(
                "/api/v3/klines",
                {
                    "symbol": symbol,
                    "interval": INTERVALS[timeframe],
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": self.page_limit,
                },
            )
            if not batch:
                break
            for k in batch:
                rows.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
            last = int(batch[-1][0])
            if len(batch) < self.page_limit or last <= cursor:
                break
            cursor = last + 1
        return [r for r in rows if start_ms <= r[0] <= end_ms]

    def fetch_latest_candles(self, symbol: str, timeframe: str, limit: int = 100) -> list[list[float]]:
        batch = self._get(
            "/api/v3/klines", {"symbol": symbol, "interval": INTERVALS[timeframe], "limit": min(limit, 1000)}
        )
        return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in batch]

    def get_supported_symbols(self) -> list[str]:
        return list(SYMBOLS)

    def health_check(self) -> ProviderHealth:
        try:
            self._get("/api/v3/klines", {"symbol": "BTCUSDT", "interval": "1d", "limit": 1})
        except ProviderError as exc:
            return ProviderHealth(False, str(exc))
        return ProviderHealth(True, "reachable")
