"""Market data provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(RuntimeError):
    """Raised when a provider cannot deliver data. The message is safe to show to users."""


@dataclass
class ProviderHealth:
    ok: bool
    detail: str


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def fetch_historical_candles(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> list[list[float]]:
        """Rows of (open_time_ms, open, high, low, close, volume), UTC, sorted, may contain duplicates."""

    @abstractmethod
    def fetch_latest_candles(self, symbol: str, timeframe: str, limit: int = 100) -> list[list[float]]: ...

    @abstractmethod
    def get_supported_symbols(self) -> list[str]: ...

    @abstractmethod
    def health_check(self) -> ProviderHealth: ...
