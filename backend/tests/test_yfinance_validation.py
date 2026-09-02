"""
Test suite for yfinance provider response validation.
Ensures empty/invalid responses are properly detected and classified.
"""
import pytest
import asyncio
from app.providers.yfinance_provider import YFinanceProvider
from app.utils.resilience import ErrorCategory, classify_error


class TestYFinanceResponseValidation:
    """Test response validation to catch Render/Linux issues with empty responses."""

    @pytest.fixture
    def provider(self):
        return YFinanceProvider()

    def test_validate_empty_dict(self, provider):
        """Empty dict from yfinance (timeout or rate limit) should be invalid."""
        info = {}
        is_valid, error = provider._validate_info_response(info, "AAPL")
        assert not is_valid
        assert "empty" in error.lower() or "required" in error.lower()

    def test_validate_none(self, provider):
        """None response should be invalid."""
        info = None
        is_valid, error = provider._validate_info_response(info, "AAPL")
        assert not is_valid

    def test_validate_real_stock_response(self, provider):
        """Real stock response with price data should be valid."""
        info = {
            "currency": "USD",
            "currentPrice": 150.25,
            "regularMarketPreviousClose": 148.75,
            "marketCap": 2_500_000_000,
            "exchange": "NASDAQ",
        }
        is_valid, error = provider._validate_info_response(info, "AAPL")
        assert is_valid
        assert error == ""

    def test_validate_etf_response(self, provider):
        """ETF response with navPrice should be valid."""
        info = {
            "currency": "USD",
            "navPrice": 420.50,
            "netExpenseRatio": 0.03,
            "quoteType": "ETF",
            "netAssets": 50_000_000_000,
        }
        is_valid, error = provider._validate_info_response(info, "VOO")
        assert is_valid

    def test_validate_error_response(self, provider):
        """Error response with quoteType=N/A should be invalid."""
        info = {
            "currency": "USD",
            "quoteType": "N/A",
        }
        is_valid, error = provider._validate_info_response(info, "INVALID")
        assert not is_valid
        assert "error" in error.lower() or "n/a" in error.lower()

    def test_validate_missing_currency(self, provider):
        """Response missing currency field should be invalid."""
        info = {
            "currentPrice": 150.0,
            # currency missing
        }
        is_valid, error = provider._validate_info_response(info, "TEST")
        assert not is_valid

    def test_validate_minimal_valid_response(self, provider):
        """Minimal response with just currency and one price field should be valid."""
        info = {
            "currency": "USD",
            "bid": 150.0,
        }
        is_valid, error = provider._validate_info_response(info, "TEST")
        assert is_valid

    def test_error_classification_provider_response_invalid(self):
        """Classification of provider response errors."""
        # Test with lowercase to match the pattern matching in classify_error
        msg = "provider response invalid: empty or non-dict response"
        cat = classify_error(message=msg)
        # Should classify as rate_limited (provider issue, not per-symbol)
        assert cat == "rate_limited", f"Expected rate_limited, got {cat}"

    def test_error_classification_missing_fields(self):
        """Classification of missing fields errors."""
        msg = "provider response missing required fields"
        cat = classify_error(message=msg)
        assert cat == "rate_limited", f"Expected rate_limited, got {cat}"

    def test_ensure_decimal_percentage(self, provider):
        """Test that decimal percentages are handled correctly."""
        from app.engines.fundamental import _ensure_decimal_percentage

        # Valid decimal percentage
        assert _ensure_decimal_percentage(0.03) == 0.03
        assert _ensure_decimal_percentage(0.34) == 0.34

        # Suspicious large values should be caught
        assert _ensure_decimal_percentage(34) == 34  # Could be 3400% or 34%
        assert _ensure_decimal_percentage(340) == 340  # Could be 34000%

    def test_percentage_to_display_dividend(self):
        """Test dividend yield percentage conversion."""
        from app.engines.fundamental import _percentage_to_display

        # 0.03 (3%) should become 3.0 for display
        assert _percentage_to_display(0.03, "dividend") == 3.0

        # 0.34 (34%) should become 34.0 for display
        assert _percentage_to_display(0.34, "dividend") == 34.0

    def test_percentage_to_display_growth(self):
        """Test growth rate percentage conversion."""
        from app.engines.fundamental import _percentage_to_display

        # 0.20 (20%) should become 20.0 for display
        assert _percentage_to_display(0.20, "growth") == 20.0

    def test_percentage_to_display_margin(self):
        """Test margin percentage conversion."""
        from app.engines.fundamental import _percentage_to_display

        # 0.15 (15%) should become 15.0 for display
        assert _percentage_to_display(0.15, "margin") == 15.0

    def test_percentage_to_display_pe_ratio(self):
        """Test that P/E ratios are not converted."""
        from app.engines.fundamental import _percentage_to_display

        # P/E ratios should NOT be multiplied
        assert _percentage_to_display(25.5, "pe_ratio") == 25.5

    def test_percentage_to_display_debt_to_equity(self):
        """Test debt to equity percentage conversion."""
        from app.engines.fundamental import _percentage_to_display

        # 0.8 (80%) should become 80.0 for display
        assert _percentage_to_display(0.8, "debt_to_equity") == 80.0

        # 1.5 (150%) should become 150.0 for display
        assert _percentage_to_display(1.5, "debt_to_equity") == 150.0


class TestYFinanceProviderResilience:
    """Test resilience features of the yfinance provider."""

    def test_provider_detects_empty_response(self):
        """Provider should detect and classify empty responses as rate_limited."""
        provider = YFinanceProvider()

        # Simulate what happens when yfinance returns empty dict
        # This would be caught during _fetch and raise RuntimeError
        empty_info = {}
        is_valid, error = provider._validate_info_response(empty_info, "TEST")

        assert not is_valid
        # The error message indicates a provider issue
        assert "empty" in error.lower() or "required" in error.lower()
        # The error should be classified as a provider-level issue
        msg = f"Provider response invalid: {error}"
        cat = classify_error(message=msg)
        assert cat == "rate_limited", f"Expected rate_limited for '{msg}', got {cat}"

    def test_circuit_breaker_trips_on_provider_errors(self):
        """Circuit breaker should trip on provider-level errors."""
        from app.utils.resilience import CircuitBreaker, ErrorCategory

        breaker = CircuitBreaker("test", failure_threshold=3)

        # Simulate 3 provider-level failures
        for _ in range(3):
            breaker.record_failure(ErrorCategory.RATE_LIMITED)

        # Should be open now
        assert not breaker.allow_request()
        assert breaker.state == "open"

        # Simulate recovery
        breaker.record_success()
        assert breaker.allow_request()
        assert breaker.state == "closed"
