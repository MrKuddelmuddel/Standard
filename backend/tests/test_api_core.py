"""Auth, ownership isolation, strategies and versions, market data, backtests, validation, discovery, jobs."""

from __future__ import annotations

import pytest

from tests.api_helpers import EMA_DEF, H, auth, client, demo_source, register, strategy  # noqa: F401


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["live_trading"] is False


# ------------------------------------------------------------------ auth
def test_register_login_logout_cycle(client):
    r = client.post("/api/v1/auth/register", json={"email": "x@example.com", "password": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    register(client, "x@example.com")
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": "x@example.com", "password": "correct horse battery"}
        ).status_code
        == 409
    )
    bad = client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "wrong password!!"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"
    ok = client.post("/api/v1/auth/login", json={"email": "X@example.com", "password": "correct horse battery"})
    assert ok.status_code == 200 and "nq_session" in ok.cookies
    me = client.get("/api/v1/auth/me")  # cookie session
    assert me.json()["email"] == "x@example.com"
    assert client.post("/api/v1/auth/logout").status_code == 403  # cookie auth without CSRF header
    assert client.post("/api/v1/auth/logout", headers=H).status_code == 204
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_is_hashed_and_errors_have_no_internals(client, auth):
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models import User

    with session_scope() as db:
        u = db.scalar(select(User))
        assert u is not None and u.password_hash.startswith("scrypt$") and "correct horse" not in u.password_hash
    r = client.get("/api/v1/strategies/does-not-exist", headers=auth)
    assert r.status_code == 404 and set(r.json()["error"]) == {"code", "message", "details", "request_id"}


def test_owner_isolation(client, auth):
    src = demo_source(client, auth)
    s = strategy(client, auth)
    bt = client.post(
        "/api/v1/backtests",
        json={"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"]},
        headers=auth,
    ).json()
    other = register(client, "b@example.com")
    assert client.get(f"/api/v1/strategies/{s['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/backtests/{bt['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/market-data/sources/{src['id']}", headers=other).status_code == 404
    r = client.post(
        "/api/v1/backtests",
        json={"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"]},
        headers=other,
    )
    assert r.status_code == 404
    assert client.get("/api/v1/strategies", headers=other).json()["total"] == 0


# ------------------------------------------------------------------ strategies
def test_strategy_versions_are_immutable_and_deduplicated(client, auth):
    bad = client.post(
        "/api/v1/strategies", json={"name": "x", "definition": {**EMA_DEF, "timeframe": "2h"}}, headers=auth
    )
    assert (
        bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_strategy" and bad.json()["error"]["details"]
    )
    s = strategy(client, auth)
    v1 = s["current_version"]
    same = client.patch(f"/api/v1/strategies/{s['id']}", json={"definition": EMA_DEF}, headers=auth).json()
    assert same["current_version_id"] == v1["id"] and same["version_count"] == 1
    changed = {**EMA_DEF, "indicators": [{**EMA_DEF["indicators"][0], "period": 12}, *EMA_DEF["indicators"][1:]]}
    s2 = client.patch(
        f"/api/v1/strategies/{s['id']}", json={"definition": changed, "note": "faster"}, headers=auth
    ).json()
    assert (
        s2["current_version"]["version_number"] == 2 and s2["current_version"]["canonical_hash"] != v1["canonical_hash"]
    )
    versions = client.get(f"/api/v1/strategies/{s['id']}/versions", headers=auth).json()
    assert [v["version_number"] for v in versions] == [2, 1]

    from app.db.session import session_scope
    from app.models import StrategyVersion

    with pytest.raises(ValueError, match="immutable"), session_scope() as db:
        v = db.get(StrategyVersion, v1["id"])
        assert v is not None
        v.note = "tamper"


def test_duplicate_archive_export_import(client, auth):
    s = strategy(client, auth)
    dup = client.post(f"/api/v1/strategies/{s['id']}/duplicate", headers=auth).json()
    assert (
        dup["name"].endswith("(copy)")
        and dup["current_version"]["canonical_hash"] == s["current_version"]["canonical_hash"]
    )
    arch = client.post(f"/api/v1/strategies/{s['id']}/archive", headers=auth).json()
    assert arch["status"] == "archived"
    assert client.patch(f"/api/v1/strategies/{s['id']}", json={"name": "y"}, headers=auth).status_code == 409
    assert client.get("/api/v1/strategies?status=archived", headers=auth).json()["total"] == 1
    doc = client.get(f"/api/v1/strategies/{s['id']}/export", headers=auth).json()
    assert doc["format"] == "nexus-quant-strategy"
    imp = client.post("/api/v1/strategies/import", json={"document": doc}, headers=auth).json()
    assert imp["origin"] == "imported" and imp["current_version"]["canonical_hash"] == doc["strategy"]["canonical_hash"]
    assert (
        client.post("/api/v1/strategies/import", json={"document": {"format": "other"}}, headers=auth).status_code
        == 422
    )


def test_validate_endpoint(client, auth):
    ok = client.post("/api/v1/strategies/validate", json={"definition": EMA_DEF}, headers=auth).json()
    assert ok["valid"] and len(ok["canonical_hash"]) == 64
    bad = client.post(
        "/api/v1/strategies/validate", json={"definition": {**EMA_DEF, "direction": "short"}}, headers=auth
    ).json()
    assert not bad["valid"] and any("futures_sim" in i["message"] for i in bad["issues"])


# ------------------------------------------------------------------ market data
CSV = "timestamp,open,high,low,close,volume\n" + "\n".join(
    f"{1704067200000 + k * 3600000},{100 + k},{101 + k},{99 + k},{100.5 + k},10" for k in range(50)
)


def test_csv_import_is_idempotent_and_versioned(client, auth):
    files = {"file": ("btc.csv", CSV, "text/csv")}
    r1 = client.post(
        "/api/v1/market-data/import-csv", data={"symbol": "BTCUSDT", "timeframe": "1h"}, files=files, headers=auth
    )
    assert r1.status_code == 201, r1.text
    s1 = r1.json()
    assert s1["import"]["inserted"] == 50 and s1["source"]["is_synthetic"] is False
    r2 = client.post(
        "/api/v1/market-data/import-csv", data={"symbol": "BTCUSDT", "timeframe": "1h"}, files=files, headers=auth
    ).json()
    assert r2["import"]["inserted"] == 0 and r2["source"]["revision"] == 2
    assert r2["source"]["fingerprint"] == s1["source"]["fingerprint"]
    bad = client.post(
        "/api/v1/market-data/import-csv",
        data={"symbol": "BTCUSDT", "timeframe": "1h"},
        files={"file": ("x.csv", "a,b\n1,2\n", "text/csv")},
        headers=auth,
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_csv"
    prev = client.get(f"/api/v1/market-data/sources/{s1['source']['id']}/candles?limit=10", headers=auth).json()
    assert len(prev["rows"]) == 10


def test_demo_data_is_flagged(client, auth):
    src = demo_source(client, auth, bars=600)
    assert src["is_synthetic"] and src["row_count"] == 600 and src["provider"] == "synthetic"


def test_provider_fetch_error_is_visible(client, auth, monkeypatch):
    from app.services import market_data
    from quant.data.providers.base import ProviderError

    def boom(*a, **k):
        raise ProviderError("Binance returned HTTP 403.")

    monkeypatch.setattr(market_data.BinanceSpotProvider, "fetch_historical_candles", boom)
    r = client.post(
        "/api/v1/market-data/fetch",
        json={"symbol": "BTCUSDT", "timeframe": "1h", "start": "2024-01-01T00:00:00Z", "end": "2024-01-02T00:00:00Z"},
        headers=auth,
    )
    assert r.status_code == 502 and "403" in r.json()["error"]["message"]


# ------------------------------------------------------------------ backtests
def test_backtest_end_to_end_reproducible(client, auth):
    src = demo_source(client, auth)
    s = strategy(client, auth)
    body = {"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"], "initial_capital": 5000}
    a = client.post("/api/v1/backtests", json=body, headers=auth)
    assert a.status_code == 202
    a = a.json()
    assert a["status"] == "completed", a
    assert a["engine_version"] and a["execution_model_version"] == "next_open_v1"
    assert a["config_json"]["data_fingerprint"] == src["fingerprint"]
    assert a["config_json"]["strategy_hash"] == s["current_version"]["canonical_hash"]
    assert any("Synthetic" in w for w in a["result"]["warnings"])
    assert a["result"]["curve"] and a["result"]["curve_columns"] == ["time", "equity", "drawdown"]
    trades = client.get(f"/api/v1/backtests/{a['id']}/trades?limit=100", headers=auth).json()
    assert trades["total"] == a["metrics"]["trade_count"]
    metrics = client.get(f"/api/v1/backtests/{a['id']}/metrics", headers=auth).json()["metrics"]
    assert "net_return" in metrics and "profit_factor" in metrics
    b = client.post("/api/v1/backtests", json=body, headers=auth).json()
    assert b["metrics"] == a["metrics"]
    hist = client.get(f"/api/v1/strategies/{s['id']}/backtests", headers=auth).json()
    assert hist["total"] == 2


def test_backtest_rejects_incompatible_data(client, auth):
    src = demo_source(client, auth, timeframe="4h", bars=600)
    s = strategy(client, auth)
    r = client.post(
        "/api/v1/backtests",
        json={"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"]},
        headers=auth,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "timeframe_mismatch"


def test_backtest_fails_cleanly_on_insufficient_data(client, auth):
    src = demo_source(client, auth, bars=500)
    d = {
        **EMA_DEF,
        "indicators": [
            {"id": "fast", "type": "ema", "period": 10},
            {"id": "slow", "type": "ema", "period": 499},
            {"id": "atr14", "type": "atr", "period": 14},
        ],
    }
    s = strategy(client, auth, d)
    r = client.post(
        "/api/v1/backtests",
        json={"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"]},
        headers=auth,
    ).json()
    assert r["status"] == "failed" and r["error_code"] == "insufficient_data" and r["metrics"] is None
    m = client.get(f"/api/v1/backtests/{r['id']}/metrics", headers=auth)
    assert m.status_code == 409


def test_validation_run(client, auth):
    src = demo_source(client, auth, bars=4000)
    s = strategy(client, auth)
    v = client.post(
        "/api/v1/validations",
        json={"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"], "folds": 3},
        headers=auth,
    ).json()
    assert v["status"] == "completed", v
    assert set(v["metrics"]["splits"]) == {"train", "validation", "test"}
    assert any("Synthetic" in w for w in v["warnings"])
    bad = client.post(
        "/api/v1/validations",
        json={
            "strategy_version_id": s["current_version_id"],
            "market_data_source_id": src["id"],
            "train_fraction": 0.8,
            "validation_fraction": 0.2,
        },
        headers=auth,
    )
    assert bad.status_code == 422


def test_discovery_and_save_candidate(client, auth):
    src = demo_source(client, auth, bars=5000)
    cfg = {"templates": ["ema_cross", "breakout"], "max_candidates": 20, "min_trades": 10}
    d = client.post(
        "/api/v1/discoveries", json={"market_data_source_id": src["id"], "config": cfg}, headers=auth
    ).json()
    assert d["status"] == "completed", d
    assert d["report"]["ranking_version"] == "rank_v1" and d["report"]["tested"] > 0
    assert d["job"]["progress_total"] and d["job"]["progress_current"] == d["job"]["progress_total"]
    cands = client.get(f"/api/v1/discoveries/{d['id']}/candidates?limit=100", headers=auth).json()
    assert cands["total"] == d["candidate_count"]
    rejected = [c for c in cands["items"] if c["status"] == "rejected"]
    assert all(c["rejection_reason"] for c in rejected)
    pick = cands["items"][0]
    saved = client.post(f"/api/v1/discoveries/{d['id']}/candidates/{pick['id']}/save", headers=auth)
    assert saved.status_code == 201 and saved.json()["origin"] == "discovery"
    assert client.post(f"/api/v1/discoveries/{d['id']}/candidates/{pick['id']}/save", headers=auth).status_code == 409
    bad = client.post(
        "/api/v1/discoveries",
        json={"market_data_source_id": src["id"], "config": {"max_candidates": 10_000}},
        headers=auth,
    )
    assert bad.status_code == 422


# ------------------------------------------------------------------ jobs
def test_job_claim_is_atomic_and_queued_jobs_can_be_cancelled(tmp_path):
    from tests.api_helpers import make_client

    c = make_client(tmp_path, JOBS_MODE="external")
    with c:
        a = register(c)
        src = demo_source(c, a, bars=600)
        s = strategy(c, a)
        bt = c.post(
            "/api/v1/backtests",
            json={"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"]},
            headers=a,
        ).json()
        assert bt["status"] == "queued" and bt["job"]["status"] == "queued"
        from app.db.session import session_scope
        from app.services import jobs

        with session_scope() as db:
            job_id = bt["job"]["id"]
            assert jobs.claim(db, job_id) is True
            assert jobs.claim(db, job_id) is False
        bt2 = c.post(
            "/api/v1/backtests",
            json={"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"]},
            headers=a,
        ).json()
        r = c.post(f"/api/v1/backtests/{bt2['id']}/cancel", headers=a).json()
        assert r["status"] == "cancelled"
        assert c.get(f"/api/v1/backtests/{bt2['id']}", headers=a).json()["status"] == "cancelled"
        assert jobs.work_once() == 0  # nothing queued any more


def test_parallel_job_limit_and_rate_limit(tmp_path):
    from tests.api_helpers import make_client

    c = make_client(tmp_path, JOBS_MODE="external", MAX_PARALLEL_JOBS_PER_USER="2", EXPENSIVE_REQUESTS_PER_MINUTE="5")
    with c:
        a = register(c)
        src = demo_source(c, a, bars=600)
        s = strategy(c, a)
        body = {"strategy_version_id": s["current_version_id"], "market_data_source_id": src["id"]}
        assert c.post("/api/v1/backtests", json=body, headers=a).status_code == 202
        assert c.post("/api/v1/backtests", json=body, headers=a).status_code == 202
        third = c.post("/api/v1/backtests", json=body, headers=a)
        assert third.status_code == 429 and third.json()["error"]["code"] == "too_many_jobs"
        codes = [c.post("/api/v1/backtests", json=body, headers=a).status_code for _ in range(3)]
        assert 429 in codes
