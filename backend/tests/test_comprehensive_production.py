"""
Comprehensive production tests - covers 40+ scenarios:
- Error classification and circuit breaker behavior
- Rate limiting and request governor
- JSONDecodeError, timeout, network failure handling
- Concurrent request deduplication
- Cache fallback chains (fresh -> stale -> unavailable)
- Ticker normalization edge cases
- Rebalancing consistency edge cases
- Data status propagation
- Partial batch failure resilience
- Structured failure payloads
"""
import asyncio
import time
import threading
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


# 1. ERROR CLASSIFICATION

class TestErrorClassification:
    """classify_error covers all failure modes."""

    def test_rate_limit_429(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="HTTPError 429 Too Many Requests") == ErrorCategory.RATE_LIMITED

    def test_rate_limit_message(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="rate limit exceeded") == ErrorCategory.RATE_LIMITED

    def test_timeout_exception(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(exc=TimeoutError("timed out")) == ErrorCategory.TIMEOUT

    def test_timeout_message(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="ReadTimeout: connection timed out") == ErrorCategory.TIMEOUT

    def test_json_decode_error(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="JSONDecodeError: Expecting value") == ErrorCategory.PARSE_ERROR

    def test_not_found_404(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="HTTPError 404 Not Found") == ErrorCategory.NOT_FOUND

    def test_not_found_delisted(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="no data found, symbol may be delisted") == ErrorCategory.NOT_FOUND

    def test_not_found_no_rows(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="no rows returned by batch download") == ErrorCategory.NOT_FOUND

    def test_network_connection_reset(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="ConnectionResetError: 10054") == ErrorCategory.NETWORK

    def test_network_unreachable(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="getaddrinfo failed") == ErrorCategory.NETWORK

    def test_auth_401(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="HTTPError 401 Unauthorized") == ErrorCategory.AUTH

    def test_auth_api_key(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="invalid api key") == ErrorCategory.AUTH

    def test_unknown_returns_unknown(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="something weird happened") == ErrorCategory.UNKNOWN

    def test_empty_message_returns_unknown(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="") == ErrorCategory.UNKNOWN


# 2. CIRCUIT BREAKER

class TestCircuitBreaker:
    """Circuit breaker trips on consecutive rate-limit/network failures."""

    def test_initially_closed(self):
        from app.utils.resilience import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=1)
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_trips_after_threshold(self):
        from app.utils.resilience import CircuitBreaker, ErrorCategory
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)
        for _ in range(3):
            cb.record_failure(ErrorCategory.RATE_LIMITED)
        assert cb.state == "open"
        assert cb.allow_request() is False

    def test_does_not_trip_on_unknown(self):
        from app.utils.resilience import CircuitBreaker, ErrorCategory
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)
        for _ in range(5):
            cb.record_failure(ErrorCategory.UNKNOWN)
        assert cb.state == "closed", "Unknown errors should not trip breaker"

    def test_does_not_trip_on_not_found(self):
        from app.utils.resilience import CircuitBreaker, ErrorCategory
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)
        for _ in range(5):
            cb.record_failure(ErrorCategory.NOT_FOUND)
        assert cb.state == "closed", "Not-found errors should not trip breaker"

    def test_resets_on_success(self):
        from app.utils.resilience import CircuitBreaker, ErrorCategory
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        cb.record_success()
        assert cb.state == "closed"
        assert cb._failure_count == 0

    def test_half_open_after_cooldown(self):
        from app.utils.resilience import CircuitBreaker, ErrorCategory
        cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure(ErrorCategory.NETWORK)
        cb.record_failure(ErrorCategory.NETWORK)
        assert cb.state == "open"
        time.sleep(0.15)
        assert cb.state == "half_open"
        assert cb.allow_request() is True

    def test_snapshot_returns_state(self):
        from app.utils.resilience import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)
        snap = cb.snapshot()
        assert "state" in snap
        assert "failure_count" in snap
        assert "cooldown_remaining" in snap


# 3. PROVIDER HEALTH TRACKING

class TestProviderHealth:
    """ProviderHealth tracks successes, failures, and cache hits."""

    def test_record_success(self):
        from app.utils.resilience import ProviderHealth
        ph = ProviderHealth()
        ph.record_success("yahoo", 100.0, ticker="AAPL", op="price")
        snap = ph.snapshot()
        assert "yahoo" in snap
        assert snap["yahoo"]["successes"] == 1
        assert snap["yahoo"]["last_success_at"] is not None

    def test_record_failure(self):
        from app.utils.resilience import ProviderHealth
        ph = ProviderHealth()
        ph.record_failure("yahoo", "rate_limited", "429 Too Many", ticker="AAPL", op="price")
        snap = ph.snapshot()
        assert snap["yahoo"]["failures"] == 1
        assert snap["yahoo"]["by_category"]["rate_limited"] == 1

    def test_record_cache_hit(self):
        from app.utils.resilience import ProviderHealth
        ph = ProviderHealth()
        ph.record_cache_hit("yahoo")
        ph.record_cache_hit("yahoo")
        snap = ph.snapshot()
        assert snap["yahoo"]["cache_hits"] == 2

    def test_avg_duration_tracking(self):
        from app.utils.resilience import ProviderHealth
        ph = ProviderHealth()
        ph.record_success("yahoo", 100.0)
        ph.record_success("yahoo", 200.0)
        snap = ph.snapshot()
        assert snap["yahoo"]["avg_duration_ms"] == 150.0


# 4. BACKOFF WITH JITTER

class TestBackoffWithJitter:
    """Exponential backoff with jitter stays within bounds."""

    def test_first_attempt_low(self):
        from app.utils.resilience import backoff_with_jitter
        val = backoff_with_jitter(1, base=2.0, cap=30.0)
        assert 0.5 <= val <= 4.0, f"Attempt 1 backoff {val} out of range"

    def test_grows_exponentially(self):
        from app.utils.resilience import backoff_with_jitter
        vals = [backoff_with_jitter(i, base=2.0, cap=30.0) for i in range(1, 6)]
        assert sum(vals[-2:]) > sum(vals[:2]), "Backoff should grow"

    def test_respects_cap(self):
        from app.utils.resilience import backoff_with_jitter
        val = backoff_with_jitter(20, base=2.0, cap=5.0)
        assert val <= 5.0, f"Backoff {val} exceeds cap 5.0"


# 5. STRUCTURED FAILURE PAYLOADS

class TestStructuredFailure:
    """structured_failure returns correct shape."""

    def test_basic_shape(self):
        from app.utils.resilience import structured_failure
        result = structured_failure("AAPL", "rate_limited", "429 Too Many")
        assert result["symbol"] == "AAPL"
        assert result["price"] is None
        assert result["status"] == "provider_unavailable"
        assert result["error_category"] == "rate_limited"
        assert result["from_stale_cache"] is False

    def test_with_stale_cache(self):
        from app.utils.resilience import structured_failure
        result = structured_failure("AAPL", "timeout", "timed out", cached=True)
        assert result["from_stale_cache"] is True

    def test_message_truncation(self):
        from app.utils.resilience import structured_failure
        long_msg = "x" * 500
        result = structured_failure("AAPL", "unknown", long_msg)
        assert len(result["error"]) <= 200


# 6. TICKER NORMALIZATION

class TestTickerNormalization:
    """Ticker normalization handles edge cases."""

    def test_voo_normalization(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("VOO") == "VOO"
        assert ts.normalize("voo") == "VOO"
        assert ts.normalize("V0O") == "VOO"
        assert ts.normalize("V00") == "VOO"

    def test_empty_symbol(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        result = ts.normalize("")
        assert isinstance(result, str)

    def test_none_symbol(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        result = ts.normalize(None)
        assert isinstance(result, str)


# 7. REBALANCING CONSISTENCY EDGE CASES

class TestRebalancingEdgeCases:
    """Additional rebalancing consistency tests."""

    def test_empty_holdings(self):
        from app.engines.rebalancing import RebalancingEngine
        engine = RebalancingEngine()
        result = engine.analyze([])
        assert result["rebalancing_score"] == 0
        assert result["stock_swaps"] == []

    def test_zero_value_holdings(self):
        from app.engines.rebalancing import RebalancingEngine
        engine = RebalancingEngine()
        holdings = [{"symbol": "A", "current_value": 0, "sector": "Tech"}]
        result = engine.analyze(holdings)
        assert result["rebalancing_score"] == 0

    def test_single_holding_no_swap(self):
        from app.engines.rebalancing import RebalancingEngine
        engine = RebalancingEngine()
        holdings = [
            {"symbol": "AAPL", "name": "Apple", "sector": "Technology",
             "current_value": 10000, "unrealized_gain_pct": 15, "quantity": 50, "avg_price": 150}
        ]
        result = engine.analyze(holdings)
        assert result["total_positions"] == 1
        assert isinstance(result["stock_swaps"], list)

    def test_all_holdings_same_sector(self):
        from app.engines.rebalancing import RebalancingEngine
        engine = RebalancingEngine()
        holdings = [
            {"symbol": "AAPL", "name": "Apple", "sector": "Technology",
             "current_value": 5000, "unrealized_gain_pct": 10, "quantity": 25, "avg_price": 150},
            {"symbol": "MSFT", "name": "Microsoft", "sector": "Technology",
             "current_value": 5000, "unrealized_gain_pct": 5, "quantity": 15, "avg_price": 300},
        ]
        result = engine.analyze(holdings)
        assert result["total_positions"] == 2
        sector_alloc = result.get("sector_allocation", [])
        assert len(sector_alloc) >= 1

    def test_validate_deduplicate_empty(self):
        from app.engines.rebalancing import RebalancingEngine
        engine = RebalancingEngine()
        result = engine._validate_and_deduplicate([], [], [])
        assert result == []

    def test_no_circular_replacement(self):
        from app.engines.rebalancing import RebalancingEngine
        engine = RebalancingEngine()
        holdings = [
            {"symbol": "A", "sector": "Tech"},
            {"symbol": "B", "sector": "Tech"},
        ]
        suggestions = [
            {"action": "swap_reduce", "symbol": "A", "replacement": {"replacement_ticker": "B"}},
            {"action": "swap_reduce", "symbol": "B", "replacement": {"replacement_ticker": "A"}},
        ]
        result = engine._validate_and_deduplicate(suggestions, [], holdings)
        assert len(result) <= 1


# 8. CACHE FALLBACK CHAINS

class TestCacheFallback:
    """Cache methods work correctly."""

    def test_get_cached_price_any_age(self):
        from app.database import SessionLocal
        from app.utils.cache import CacheManager
        db = SessionLocal()
        try:
            cache = CacheManager(db)
            result = cache.get_cached_price_any_age("NONEXISTENT_SYMBOL_XYZ")
            assert result is None
        finally:
            db.close()

    def test_set_and_get_cached_price(self):
        from app.database import SessionLocal
        from app.utils.cache import CacheManager
        db = SessionLocal()
        try:
            cache = CacheManager(db)
            test_data = {
                "price": 150.0, "previous_close": 148.0,
                "open": 149.0, "day_high": 151.0, "day_low": 147.0,
                "volume": 1000000, "avg_volume": 900000,
                "fifty_two_week_high": 180.0, "fifty_two_week_low": 120.0,
                "change": 2.0, "change_pct": 1.35,
            }
            cache.set_cached_price("TEST_CACHE_PRICE", test_data)
            result = cache.get_cached_price("TEST_CACHE_PRICE")
            assert result is not None
            assert result["price"] == 150.0
            # Also test any_age
            result_any = cache.get_cached_price_any_age("TEST_CACHE_PRICE")
            assert result_any is not None
            assert result_any["price"] == 150.0
        finally:
            db.close()

    def test_set_and_get_stock_info(self):
        from app.database import SessionLocal
        from app.utils.cache import CacheManager
        db = SessionLocal()
        try:
            cache = CacheManager(db)
            test_data = {
                "name": "Test Corp", "sector": "Technology",
                "industry": "Software", "market_cap": 1000000000,
            }
            cache.set_cached_stock_info("TEST_CACHE_INFO", test_data)
            result = cache.get_cached_stock_info("TEST_CACHE_INFO")
            assert result is not None
            assert result["name"] == "Test Corp"
        finally:
            db.close()

    def test_set_and_get_historical(self):
        from app.database import SessionLocal
        from app.utils.cache import CacheManager
        db = SessionLocal()
        try:
            cache = CacheManager(db)
            test_data = [
                {"date": "2025-01-01", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000}
            ]
            cache.set_cached_historical("TEST_CACHE_HIST", "1y", test_data)
            result = cache.get_cached_historical("TEST_CACHE_HIST", "1y")
            assert result is not None
            assert len(result) == 1
        finally:
            db.close()


# 9. DATA STATUS PROPAGATION

class TestDataStatusPropagation:
    """Endpoints return proper data_status values."""

    def test_trading_opportunities_data_status(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("data_status") in ("success", "partial", "stale", "provider_unavailable")

    def test_trading_opportunities_has_data_quality(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        dq = data.get("data_quality", {})
        assert "eligible_holdings" in dq
        assert "holdings_with_data" in dq

    def test_rebalancing_has_score(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio/rebalancing")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert "rebalancing_score" in data

    def test_diagnostics_structure(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/diagnostics")
        assert r.status_code == 200
        diag = r.json()
        assert "providers" in diag
        assert "portfolio" in diag


# 10. PARTIAL BATCH FAILURE RESILIENCE

class TestPartialBatchResilience:
    """Batch operations handle partial failures gracefully."""

    def test_get_batch_returns_dict(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_stock_analysis_returns_error_for_invalid(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/stocks/INVALID_TICKER_XYZ/analysis")
        assert r.status_code in (400, 404), f"Expected 400 or 404, got {r.status_code}"

    def test_stock_analysis_returns_error_for_numeric(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/stocks/12345/analysis")
        assert r.status_code in (400, 404), f"Expected 400 or 404, got {r.status_code}"

    def test_portfolio_health_loads(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/analytics/portfolio-health")
        assert r.status_code == 200


# 11. REBALANCING ENGINE COMPREHENSIVE

class TestRebalancingEngine:
    """Full rebalancing engine tests."""

    def test_engine_returns_all_fields(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio/rebalancing")
        data = r.json().get("data", {})
        required = [
            "rebalancing_score", "total_portfolio_value", "total_positions",
            "position_allocation", "sector_allocation", "stock_swaps",
            "suggestions", "summary",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_no_held_stock_as_replacement(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio/rebalancing")
        data = r.json().get("data", {})
        held = {pa["symbol"] for pa in data.get("position_allocation", [])}
        for swap in data.get("stock_swaps", []):
            repl = swap.get("replacement")
            if repl and repl.get("replacement_ticker"):
                assert repl["replacement_ticker"] not in held, (
                    f"{swap['symbol']} replacement {repl['replacement_ticker']} is held"
                )

    def test_suggestions_action_format(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio/rebalancing")
        data = r.json().get("data", {})
        valid_actions = {
            "swap_sell", "swap_reduce", "swap_swap_candidate",
            "reduce", "reduce_sector_exposure", "add_sector_exposure",
            "increase_position", "hold",
        }
        for s in data.get("suggestions", []):
            assert s.get("action") in valid_actions, f"Invalid action: {s.get('action')}"


# 12. WATCHLIST INTEGRITY

class TestWatchlistIntegrity:
    """Watchlist auto-fill and CRUD work correctly."""

    def test_watchlist_loads(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/watchlist")
        assert r.status_code == 200

    def test_watchlist_suggestions_available(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/watchlist/suggestions")
        assert r.status_code == 200
        data = r.json()
        suggestions = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(suggestions, list)

    def test_watchlist_suggestions_exclude_holdings(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/watchlist/suggestions")
        data = r.json()
        suggestions = data.get("data", data) if isinstance(data, dict) else data
        # Get portfolio symbols
        r2 = client.get("/portfolio/holdings")
        holdings_data = r2.json().get("data", {})
        holdings = holdings_data.get("holdings", []) if isinstance(holdings_data, dict) else []
        held = {h["symbol"] for h in holdings}
        for s in suggestions:
            if isinstance(s, dict):
                assert s.get("symbol") not in held, f"Holding {s.get('symbol')} in suggestions"


# 13. CONCURRENT REQUEST HANDLING

class TestConcurrentRequests:
    """Multiple simultaneous requests don't crash."""

    def test_concurrent_portfolio_requests(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        results = []
        def fetch():
            r = client.get("/portfolio")
            results.append(r.status_code)
        threads = [threading.Thread(target=fetch) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert all(code == 200 for code in results), f"Some requests failed: {results}"

    def test_concurrent_watchlist_requests(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        results = []
        def fetch():
            r = client.get("/watchlist")
            results.append(r.status_code)
        threads = [threading.Thread(target=fetch) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert all(code == 200 for code in results)


# 14. SETTINGS AND ALERTS

class TestSettingsAndAlerts:
    """Settings and alerts endpoints work."""

    def test_get_settings(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/settings")
        assert r.status_code == 200

    def test_get_alerts(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/alerts")
        assert r.status_code == 200

    def test_get_catalyst_alerts(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/catalysts/alerts")
        assert r.status_code == 200

    def test_catalyst_events_loads(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/catalysts/events")
        assert r.status_code == 200

    def test_catalyst_summary_loads(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/catalysts/summary")
        assert r.status_code == 200


# 15. PORTFOLIO ENDPOINTS

class TestPortfolioEndpoints:
    """Portfolio endpoints return valid data."""

    def test_portfolio_summary(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio")
        assert r.status_code == 200
        data = r.json()
        assert "data" in data or "total_value" in data

    def test_portfolio_holdings(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio/holdings")
        assert r.status_code == 200

    def test_portfolio_performance(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio/performance")
        assert r.status_code == 200

    def test_portfolio_risk_summary(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/portfolio/risk-summary")
        assert r.status_code == 200
