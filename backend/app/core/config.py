"""Central configuration from environment variables. All limits live here."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    nexus_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite:///./data/nexus.db"
    jobs_mode: Literal["thread", "external", "inline"] = "thread"
    worker_poll_seconds: float = 0.5
    cors_origins: list[str] = ["http://localhost:3000"]
    cookie_secure: bool = False
    session_days: int = 14
    log_level: str = "INFO"

    # Limits
    max_backtest_bars: int = 300_000
    max_discovery_candidates: int = 300
    max_discovery_seconds: float = 600.0
    job_timeout_seconds: int = 1800
    max_parallel_jobs_per_user: int = 3
    max_csv_bytes: int = 5_000_000
    max_csv_rows: int = 200_000
    max_journal_csv_rows: int = 5_000
    max_page_size: int = 100
    paper_max_bars_per_step: int = 2_000
    paper_auto_bars_per_tick: int = 5
    expensive_requests_per_minute: int = 20
    webhook_requests_per_minute: int = 30
    webhook_max_clock_skew_seconds: int = 600

    # Market data
    binance_base_url: str = "https://api.binance.com"
    market_data_timeout_seconds: float = 10.0

    # AI (optional)
    ai_provider: Literal["none", "anthropic"] = "none"
    anthropic_api_key: str | None = Field(default=None, repr=False)
    ai_model: str = "claude-opus-5-5"
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    ai_refusal_fallback: bool = True
    ai_max_tool_calls: int = 8
    ai_max_seconds: float = 90.0
    ai_max_output_tokens: int = 16_000
    ai_max_runs_per_day: int = 50

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def ai_configured(self) -> bool:
        return self.ai_provider == "anthropic" and bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
