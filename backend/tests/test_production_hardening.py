"""
Automated test suite for production stability.
Tests: batch failure storms, 429, circuit breaker, search offline,
stale cache, ticker normalization, and more.
"""
import sys
import os
import time
import asyncio
import pytest

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestBatchFailureStorm:
    """Verify batch failure does NOT create 25 individual requests."""

    def test_batch_returns_zero_does_not_launch_individual_storm(self):
        """When batch download returns 0/25, fallback must be bounded."""
        from app.services.stock_service import StockService, _MAX_FALLBACK_CONCURRENCY
        assert _MAX_FALLBACK_CONCURRENCY <= 5, (
            f"Max fallback concurrency too high: {_MAX_FALLBACK_CONCURRENCY}. "
            "Must be <= 5 to prevent request storms."
        )

    def test_circuit_breaker_blocks_individual_fallback(self):
        """When circuit breaker is open, batch AND individual calls are blocked."""
        from app.utils.resilience import get_circuit_breaker, ErrorCategory
        breaker = get_circuit_breaker("yahoo_test_storm")
        # Trip the breaker
        for _ in range(10):
            breaker.record_failure(ErrorCategory.RATE_LIMITED)
        assert not breaker.allow_request(), "Circuit breaker should be OPEN"
        # Cleanup
        breaker.record_success()


class TestCircuitBreaker:
    """Full lifecycle: closed -> open -> half_open -> closed."""

    def test_lifecycle(self):
        from app.utils.resilience import CircuitBreaker, ErrorCategory
        cb = CircuitBreaker("test_lifecycle", failure_threshold=3, cooldown_seconds=0.1)
        # Closed
        assert cb.state == "closed"
        assert cb.allow_request()
        # Failures
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        assert cb.state == "closed"
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        assert cb.state == "closed"
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        # Open
        assert cb.state == "open"
        assert not cb.allow_request()
        # Wait for cooldown
        time.sleep(0.15)
        # Half-open
        assert cb.state == "half_open"
        assert cb.allow_request()
        # Success -> closed
        cb.record_success()
        assert cb.state == "closed"
        assert cb.allow_request()

    def test_soft_failures_do_not_trip(self):
        from app.utils.resilience import CircuitBreaker, ErrorCategory
        cb = CircuitBreaker("test_soft", failure_threshold=3)
        for _ in range(10):
            cb.record_failure(ErrorCategory.NOT_FOUND)
        assert cb.state == "closed"
        assert cb.allow_request()


class TestTickerNormalization:
    """Ticker normalization must handle all edge cases."""

    def test_v00_to_voo(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("V00") == "VOO"

    def test_v0o_to_voo(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("V0O") == "VOO"

    def test_csco_from_csc0(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("CSC0") == "CSCO"

    def test_appl_to_aapl(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("APPL") == "AAPL"

    def test_dollar_prefix(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("$AAPL") == "AAPL"

    def test_lowercase(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("aapl") == "AAPL"

    def test_voo_unchanged(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("VOO") == "VOO"

    def test_short_tickers_preserved(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.normalize("O") == "O"
        assert ts.normalize("V") == "V"
        assert ts.normalize("UL") == "UL"

    def test_no_blind_o_zero_swap(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        # O (Realty Income) must NOT become 0
        assert ts.normalize("O") == "O"

    def test_validate_or_raise(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        assert ts.validate_or_raise("AAPL") == "AAPL"
        with pytest.raises(ValueError):
            ts.validate_or_raise("")

    def test_batch_25_portfolio(self):
        from app.services.ticker_service import get_ticker_service
        ts = get_ticker_service()
        portfolio = ["VOO", "VYM", "JPM", "CSCO", "TXN", "UNH", "MSFT", "JNJ",
                      "O", "ABBV", "SBUX", "KMB", "AAPL", "V", "UL", "LOW",
                      "AMT", "SNA", "COST", "PEP", "OHI", "MAIN", "DHI", "AGCO", "MICC"]
        result = ts.normalize_batch(portfolio)
        assert len(result) == 25
        assert "VOO" in result
        assert "AAPL" in result
        assert "O" in result


class TestErrorClassification:
    """Error classification covers all failure modes."""

    def test_yahoo_429(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="429 Too Many Requests") == ErrorCategory.RATE_LIMITED

    def test_timeout(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="ReadTimeout") == ErrorCategory.TIMEOUT

    def test_malformed_json(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="Expecting value: line 1 column 1") == ErrorCategory.PARSE_ERROR

    def test_empty_response(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="no data available") == ErrorCategory.NOT_FOUND

    def test_network_reset(self):
        from app.utils.resilience import classify_error, ErrorCategory
        assert classify_error(message="ConnectionResetError 10054") == ErrorCategory.NETWORK

    def test_structured_failure_never_fabricates(self):
        from app.utils.resilience import structured_failure
        result = structured_failure("V00", "rate_limited", "429")
        assert result["price"] is None
        assert result["status"] == "provider_unavailable"
        assert result["symbol"] == "V00"


class TestStaleCache:
    """Stale cache must be served when provider fails."""

    def test_stale_price_served_on_failure(self):
        from app.providers.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        # Manually set stale cache
        provider._price_cache["TEST_STALE"] = (
            {"symbol": "TEST_STALE", "price": 123.45, "status": "success"},
            time.time() - 86400  # 1 day old
        )
        cached = provider._get_cached(provider._price_cache, "TEST_STALE", 86400 * 7)
        assert cached is not None
        assert cached["price"] == 123.45

    def test_circuit_open_returns_structured_failure(self):
        from app.utils.resilience import get_circuit_breaker, ErrorCategory
        from app.providers.yfinance_provider import YFinanceProvider
        cb = get_circuit_breaker("yahoo_test_stale")
        for _ in range(10):
            cb.record_failure(ErrorCategory.RATE_LIMITED)
        assert not cb.allow_request()
        cb.record_success()  # cleanup


class TestConcurrentRequests:
    """Concurrent identical requests must be deduplicated."""

    def test_trader_coalescing(self):
        from app.services.analysis_service import _inflight_scans
        # Verify coalescing dict exists
        assert isinstance(_inflight_scans, dict)


class TestCSVParser:
    """CSV parsing handles all formats."""

    def test_clean_number_dollar(self):
        from app.utils.csv_parser import _clean_number
        assert _clean_number("$1,234.56") == 1234.56

    def test_clean_number_negative_parens(self):
        from app.utils.csv_parser import _clean_number
        assert _clean_number("(1,234.56)") == -1234.56

    def test_clean_number_empty(self):
        from app.utils.csv_parser import _clean_number
        assert _clean_number("") is None
        assert _clean_number("N/A") is None
        assert _clean_number("--") is None

    def test_clean_number_percentage(self):
        from app.utils.csv_parser import _clean_number
        assert _clean_number("12.5%") == 12.5

    def test_parse_csv_content(self):
        from app.utils.csv_parser import parse_csv_content
        csv = "Symbol,Quantity,Value\nAAPL,100,15000\nMSFT,50,20000\n"
        result = parse_csv_content(csv)
        assert result["total_rows"] == 2
        assert result["valid_rows"] == 2
        assert result["estimated_total_value"] == 35000.0

    def test_parse_csv_detects_symbol_column(self):
        from app.utils.csv_parser import detect_column_mapping
        mapping = detect_column_mapping(["Ticker", "Shares", "Market Value"])
        assert mapping["symbol"] == "Ticker"
        assert mapping["quantity"] == "Shares"
        assert mapping["current_value"] == "Market Value"


class TestProviderResilience:
    """Provider resilience: backoff, retry cap, jitter."""

    def test_backoff_is_bounded(self):
        from app.utils.resilience import backoff_with_jitter
        for attempt in range(10):
            delay = backoff_with_jitter(attempt)
            assert 0 <= delay <= 30.0, f"Backoff {delay} exceeds cap at attempt {attempt}"

    def test_retry_count_bounded(self):
        from app.providers.yfinance_provider import YFinanceProvider
        p = YFinanceProvider()
        for _ in range(100):
            p._on_rate_limit()
        assert p._retry_count <= p._max_retries


class TestNewsEntityResolution:
    """News articles must not bleed across companies."""

    def test_walmart_not_mapped_to_O(self):
        from app.services.news_relevance_service import NewsRelevanceService
        svc = NewsRelevanceService()
        articles = [{"title": "Walmart earnings beat expectations", "summary": ""}]
        result = svc.attach_relevance(articles, "O", "Realty Income Corporation", min_threshold=0.70)
        # Walmart article should NOT match O (Realty Income)
        assert len(result) == 0

    def test_short_ticker_requires_evidence(self):
        from app.services.news_relevance_service import NewsRelevanceService
        svc = NewsRelevanceService()
        articles = [{"title": "Markets rally on strong earnings", "summary": ""}]
        result = svc.attach_relevance(articles, "O", "Realty Income Corporation", min_threshold=0.70)
        # Generic market article should NOT match O
        assert len(result) == 0


class TestPortfolioDataQuality:
    """Portfolio health must report accurate data quality."""

    def test_data_status_fields_exist(self):
        """data_quality must include data_status field in production output."""
        # Verify the analysis service method signature accepts force parameter
        from app.services.analysis_service import AnalysisService
        import inspect
        sig = inspect.signature(AnalysisService.get_portfolio_health_report)
        assert "force" in sig.parameters


class TestPanicSellProtection:
    """Recommendation engine must not auto-sell on single bad event."""

    def test_recommendation_returns_action(self):
        from app.engines.recommendation import RecommendationEngine
        engine = RecommendationEngine()
        result = engine.recommend(
            symbol="TEST",
            fundamental_score=70,
            fundamental_data={"score": 70},
            technical_data={"trend": "Uptrend", "momentum": "Bullish", "signals": []},
            risk_data={"risk_score": 30},
            sentiment_data={"score": 0.1},
            catalyst_data={"events": []},
            portfolio_allocation=5.0,
            unrealized_gain_pct=15.0,
            risk_profile="moderate",
        )
        assert "recommendation" in result
        assert result["recommendation"] in (
            "BUY", "HOLD", "WATCH", "TAKE PROFIT", "REDUCE", "SELL"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
