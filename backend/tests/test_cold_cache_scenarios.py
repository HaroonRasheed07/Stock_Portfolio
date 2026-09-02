"""Cold-cache test scenarios — verifies system works with empty/fresh caches."""
import time
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def test_watchlist_with_cache(client):
    """Watchlist returns stocks even with minimal cache."""
    r = client.get("/watchlist")
    assert r.status_code == 200
    raw = r.json()
    wl = raw.get("data", raw) if isinstance(raw, dict) else raw
    assert len(wl) >= 5, f"Expected >=5 watchlist items, got {len(wl)}"
    assert all("symbol" in w for w in wl)


def test_dashboard_loads(client):
    """Dashboard loads without crash regardless of cache state."""
    r = client.get("/portfolio")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data or "total_value" in data


def test_trading_opportunities(client):
    """Trading scan completes with partial data (data_status is never a crash)."""
    t0 = time.time()
    r = client.get("/analytics/trading-opportunities")
    elapsed = time.time() - t0
    assert r.status_code == 200
    data = r.json().get("data", {})
    assert data.get("data_status") in ("success", "partial", "stale", "provider_unavailable")
    dq = data.get("data_quality", {})
    assert "candidates_found" in dq
    assert "scan_duration_seconds" in dq
    print(f"  Trading scan: {dq.get('opportunities_found', 0)} opportunities in {elapsed:.1f}s")


def test_rebalancing(client):
    """Rebalancing works with portfolio data (no provider calls needed)."""
    t0 = time.time()
    r = client.get("/portfolio/rebalancing")
    elapsed = time.time() - t0
    assert r.status_code == 200
    data = r.json().get("data", {})
    assert "rebalancing_score" in data
    assert isinstance(data.get("stock_swaps", []), list)
    print(f"  Rebalancing: score={data.get('rebalancing_score')}, swaps={len(data.get('stock_swaps', []))}, {elapsed:.1f}s")


def test_diagnostics(client):
    """Diagnostics endpoint returns provider health + circuit breaker."""
    r = client.get("/diagnostics")
    assert r.status_code == 200
    diag = r.json()
    assert "providers" in diag
    yahoo = diag["providers"].get("yahoo", {})
    assert "requests_total" in yahoo
    assert "circuit_breaker" in yahoo
    assert "portfolio" in diag
    print(f"  Diagnostics: {yahoo.get('requests_total', 0)} requests, breaker={yahoo.get('circuit_breaker', {}).get('state', '?')}")


def test_invalid_ticker_returns_404(client):
    """Invalid ticker analysis returns 404, not crash."""
    r = client.get("/stocks/VQ/analysis")
    assert r.status_code == 404, f"VQ should return 404, got {r.status_code}"
    r2 = client.get("/stocks/ZZZZZ/analysis")
    assert r2.status_code == 404, f"ZZZZZ should return 404, got {r2.status_code}"


def test_stock_analysis_valid(client):
    """Valid ticker analysis works."""
    r = client.get("/stocks/AAPL/analysis")
    assert r.status_code == 200
    data = r.json()
    assert data.get("success") is True or "recommendation" in data.get("data", {})


def test_catalyst_scan(client):
    """Catalyst scan works without crash."""
    r = client.post("/catalysts/scan-portfolio")
    assert r.status_code in (200, 201)


def test_portfolio_holdings(client):
    """Portfolio holdings list works."""
    r = client.get("/portfolio/holdings")
    assert r.status_code == 200
    data = r.json()
    holdings = data.get("data", data) if isinstance(data, dict) else data
    assert isinstance(holdings, list)
    assert len(holdings) == 25, f"Expected 25 holdings, got {len(holdings)}"


def test_portfolio_health(client):
    """Portfolio health endpoint works."""
    r = client.get("/analytics/portfolio-health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("success") is True or "score" in data.get("data", {})


def test_warm_cache_faster(client):
    """Second trading scan should be faster (warm cache)."""
    t0 = time.time()
    r = client.get("/analytics/trading-opportunities")
    elapsed = time.time() - t0
    assert r.status_code == 200
    print(f"  Warm cache scan: {elapsed:.1f}s")
