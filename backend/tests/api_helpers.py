from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

EMA_DEF = {
    "name": "EMA Cross",
    "symbols": ["BTCUSDT"],
    "timeframe": "1h",
    "indicators": [
        {"id": "fast", "type": "ema", "period": 10},
        {"id": "slow", "type": "ema", "period": 30},
        {"id": "atr14", "type": "atr", "period": 14},
    ],
    "entry": {"long": {"op": "crosses_above", "left": {"ind": "fast"}, "right": {"ind": "slow"}}},
    "exit": {"long": {"op": "crosses_below", "left": {"ind": "fast"}, "right": {"ind": "slow"}}},
    "risk_management": {
        "stop_loss": {"type": "atr", "value": 2, "atr_indicator": "atr14"},
        "take_profit": {"type": "r_multiple", "value": 2},
    },
}
H = {"X-Requested-With": "nexus"}


def make_client(tmp_path, **env: str) -> TestClient:
    os.environ.update(
        {
            "NEXUS_ENV": "test",
            "JOBS_MODE": "inline",
            "DATABASE_URL": f"sqlite:///{tmp_path}/test.db",
            "AI_PROVIDER": "none",
            "ANTHROPIC_API_KEY": "",
            **env,
        }
    )
    from app.core.config import get_settings
    from app.core.ratelimit import limiter
    from app.db.base import Base
    from app.db.session import get_engine, reset_engine

    get_settings.cache_clear()
    reset_engine()
    limiter.reset()
    Base.metadata.create_all(get_engine())
    from app.main import create_app

    return TestClient(create_app())


def register(client: TestClient, email: str = "a@example.com") -> dict:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    c = make_client(tmp_path)
    with c:
        yield c


@pytest.fixture
def auth(client: TestClient) -> dict:
    return register(client)


def demo_source(client: TestClient, auth: dict, bars: int = 3000, timeframe: str = "1h") -> dict:
    r = client.post(
        "/api/v1/market-data/demo",
        json={"symbol": "BTCUSDT", "timeframe": timeframe, "bars": bars, "seed": 3},
        headers=auth,
    )
    assert r.status_code == 201, r.text
    return r.json()


def strategy(client: TestClient, auth: dict, definition: dict | None = None) -> dict:
    r = client.post("/api/v1/strategies", json={"name": "EMA Cross", "definition": definition or EMA_DEF}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()
