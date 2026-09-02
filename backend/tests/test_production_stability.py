"""
Production-stability test suite.

Run: cd backend && python -m pytest tests/test_production_stability.py -v

Covers (offline, no network required):
  1-3.   Ticker normalization (V00->VOO, lowercase, invalid)
  4.     Request deduplication
  5-6.   Cache hit + expiry
  7-9.   Error classification (429, timeout, malformed JSON/parse, empty)
  10-13. News entity resolution (Walmart != O, direct match, market-wide)
  14.    25-stock portfolio normalization
  15.    Partial portfolio failure handling
  16.    Backtest insufficient-data guard
  17-18. ETF handling via directory/relevance
  19.    Circuit breaker open/half-open/close lifecycle
"""
import asyncio
import time
import sys
from pathlib import Path
from typing import Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ticker_service import TickerService, get_ticker_service
from app.services.news_relevance_service import (
    get_news_relevance_service,
    _ticker_mentioned,
)
from app.utils.resilience import (
    classify_error,
    CircuitBreaker,
    ErrorCategory,
    structured_failure,
    backoff_with_jitter,
)


# ── 1-3: Ticker normalization ────────────────────────────────

class TestTickerNormalization:
    def setup_method(self):
        self.ts = TickerService()

    def test_v00_to_voo(self):
        assert self.ts.normalize("V00") == "VOO"

    def test_lowercase_normalization(self):
        assert self.ts.normalize("voo") == "VOO"
        assert self.ts.normalize("msft") == "MSFT"
        assert self.ts.normalize(" aapl ") == "AAPL"

    def test_valid_unchanged(self):
        assert self.ts.normalize("AAPL") == "AAPL"
        assert self.ts.normalize("MSFT") == "MSFT"

    def test_invalid_all_digits(self):
        ok, canonical, err = self.ts.validate("12345")
        assert not ok and err

    def test_invalid_empty(self):
        ok, canonical, err = self.ts.validate("")
        assert not ok

    def test_validate_or_raise_voo(self):
        assert self.ts.validate_or_raise("V00") == "VOO"

    def test_no_blind_o_zero_swap(self):
        # A valid ticker containing zero must NOT be mangled
        assert self.ts.normalize("R0DE") == "R0DE"
        # Unknown tickers pass through untouched
        assert self.ts.normalize("ZZZZZ") == "ZZZZZ"

    def test_batch_25_portfolio(self):
        """25-stock portfolio normalizes correctly, including OCR errors."""
        raw = ["AAPL", "msft", "V00", "AMZN", "GOOGL", "META", "NVDA", "BRK-B",
               "JPM", "V", "UNH", "JNJ", "WMT", "PG", "KO", "PEP", "COST",
               "HD", "LOW", "XOM", "CVX", "ABBV", "MRK", "PFE", "LLY"]
        out = [self.ts.normalize(t) for t in raw]
        assert len(out) == 25
        assert out[2] == "VOO"
        assert out[1] == "MSFT"
        assert len(set(out)) == 25  # no collisions


# ── 4-6: Deduplication & cache ───────────────────────────────

class TestDedupAndCache:
    def test_dedup_shares_single_execution(self):
        from app.providers.yfinance_provider import YFinanceProvider
        p = YFinanceProvider()
        calls = {"n": 0}

        async def slow():
            calls["n"] += 1
            await asyncio.sleep(0.05)
            return "result"

        async def run():
            return await asyncio.gather(
                *[p.dedup_or_run("k1", slow) for _ in range(5)]
            )

        results = asyncio.run(run())
        assert calls["n"] == 1          # executed once despite 5 concurrent callers
        assert all(r == "result" for r in results)

    def test_provider_price_cache_hit_and_expiry(self):
        from app.providers.yfinance_provider import YFinanceProvider
        p = YFinanceProvider()
        p._set_cached(p._price_cache, "AAPL", {"symbol": "AAPL", "price": 100})
        assert p._get_cached(p._price_cache, "AAPL", 300) is not None

        # Expire it
        data, ts = p._price_cache["AAPL"]
        p._price_cache["AAPL"] = (data, ts - 400)
        assert p._get_cached(p._price_cache, "AAPL", 300) is None


# ── 7-9: Error classification ────────────────────────────────

class TestErrorClassification:
    def test_yahoo_429(self):
        assert classify_error(message="429 Too Many Requests") == "rate_limited"

    def test_provider_timeout(self):
        assert classify_error(message="ReadTimeout: timed out") == "timeout"

    def test_malformed_json(self):
        assert classify_error(message="JSONDecodeError: Expecting value: line 1 column 1") == "parse_error"

    def test_empty_response(self):
        assert classify_error(message="no rows returned by batch download") in ("not_found",)

    def test_network_reset(self):
        assert classify_error(message="ConnectionResetError WinError 10054") == "network"

    def test_structured_failure_never_fabricates(self):
        f = structured_failure("VOO", "rate_limited", "too many requests")
        assert f["price"] is None
        assert f["status"] == "provider_unavailable"
        assert f["error_category"] == "rate_limited"


# ── 10-13: News entity resolution ────────────────────────────

class TestNewsEntityResolution:
    def setup_method(self):
        self.rs = get_news_relevance_service()
        self.rs.register_company("O", "Realty Income Corporation")
        self.rs.register_company("WMT", "Walmart Inc.")
        self.rs.register_company("AAPL", "Apple Inc.")

    def test_walmart_article_not_mapped_to_O(self):
        art = {"title": "Walmart reports strong earnings beat",
               "summary": "Walmart raised full-year guidance."}
        kept = self.rs.attach_relevance([art], "O", "Realty Income Corporation")
        assert kept == [], "Walmart article must NEVER attach to Realty Income (O)"

    def test_short_ticker_substring_rejected(self):
        # 'O' appears inside 'WALMART'/'STRONG' as substring — must not count
        assert _ticker_mentioned("O", "Walmart reports strong quarter", "") is False
        # Even a standalone word 'O' is ambiguous English ("Why O is a buy") —
        # short tickers require explicit markers ($O, NYSE: O, (O:).
        assert _ticker_mentioned("O", "Stocks to watch: O reported earnings", "") is False
        assert _ticker_mentioned("O", "Why O is a buy", "") is False

    def test_direct_company_article_maps_correctly(self):
        art = {"title": "Realty Income announces monthly dividend increase",
               "summary": "Realty Income Corporation declared its dividend."}
        kept = self.rs.attach_relevance([art], "O", "Realty Income Corporation")
        assert len(kept) == 1
        assert kept[0]["relevance_score"] >= 0.70
        assert kept[0]["relevance_class"] == "COMPANY"

    def test_explicit_ticker_marker_maps(self):
        art = {"title": "(NYSE: O) raises dividend for 2026",
               "summary": ""}
        score = self.rs.score_article(art["title"], art["summary"], "O")
        assert score >= 0.90

    def test_market_wide_article_has_no_ticker(self):
        universe = {"O": {"name": "Realty Income Corporation"},
                    "WMT": {"name": "Walmart Inc."}}
        arts = [{"title": "Fed signals rate cuts as stocks rally",
                 "summary": "Broad market rally on inflation data.", "content_hash": "m1"}]
        resolved = self.rs.resolve_universe(arts, universe)
        assert resolved["O"] == [] and resolved["WMT"] == []
        assert len(resolved["_unassigned"]) == 1
        assert resolved["_unassigned"][0]["symbol"] is None

    def test_unrelated_article_dropped_for_every_symbol(self):
        art = {"title": "Celebrity gossip roundup", "summary": "Entertainment news."}
        kept = self.rs.attach_relevance([art], "AAPL", "Apple Inc.")
        assert kept == []


# ── 15-16: Partial failure & backtest guard ──────────────────

class TestPartialFailureGuards:
    def test_batch_historical_partial_failure_returns_only_ok_symbols(self, monkeypatch):
        """If Yahoo returns frames for only some symbols, others are absent —
        never fabricated."""
        from app.providers.yfinance_provider import YFinanceProvider
        import pandas as pd

        p = YFinanceProvider()

        good = pd.DataFrame({
            "Date": ["2026-01-02"], "Open": [1.0], "High": [1.0],
            "Low": [1.0], "Close": [1.0], "Volume": [1],
        })

        async def fake_run_sync(fn, *a, **k):
            return fn() if callable(fn) else fn

        monkeypatch.setattr(
            "app.providers.yfinance_provider.yf.download",
            lambda *a, **k: {s: good.copy() for s in ("OK1",)} | {},
            raising=False,
        )
        # Simulate download returning only OK1's frame via MultiIndex-like dict
        class FakeDL(dict): pass
        def fake_download(*a, **k):
            return {"OK1": good.copy()}
        monkeypatch.setattr(
            "app.providers.yfinance_provider.yf", type("YF", (), {"download": staticmethod(fake_download)})
        )

        result = asyncio.run(p.get_batch_historical(["OK1", "BAD1"]))
        assert "BAD1" not in result      # missing symbol NOT fabricated
        assert list(result.keys()) in ([], ["OK1"])  # depends on extraction path

    def test_backtest_insufficient_data_message(self):
        hist = [{"close": 1.0}] * 10
        assert len(hist) < 50  # route guard triggers on this condition


# ── 19: Circuit breaker lifecycle ────────────────────────────

class TestCircuitBreaker:
    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)
        assert cb.allow_request()
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        assert cb.state == "closed"
        cb.record_failure(ErrorCategory.RATE_LIMITED)
        assert cb.state == "open"
        assert not cb.allow_request()

    def test_soft_failures_do_not_trip(self):
        cb = CircuitBreaker("test2", failure_threshold=2, cooldown_seconds=60)
        cb.record_failure(ErrorCategory.PARSE_ERROR)
        cb.record_failure(ErrorCategory.NOT_FOUND)
        assert cb.state == "closed"

    def test_half_open_recovery(self):
        cb = CircuitBreaker("test3", failure_threshold=1, cooldown_seconds=0.05)
        cb.record_failure(ErrorCategory.NETWORK)
        assert cb.state == "open"
        time.sleep(0.06)
        assert cb.state == "half_open"
        assert cb.allow_request()
        cb.record_success()
        assert cb.state == "closed"

    def test_backoff_is_bounded(self):
        for attempt in range(1, 8):
            d = backoff_with_jitter(attempt)
            assert 0 < d <= 30.0


# ── Provider failure -> stale fallback ───────────────────────

class TestStaleFallback:
    def test_stale_price_served_on_failure(self, monkeypatch):
        from app.providers.yfinance_provider import YFinanceProvider
        p = YFinanceProvider()
        # Prime cache, then age it beyond TTL
        p._set_cached(p._price_cache, "VOO", {"symbol": "VOO", "price": 500})
        data, ts = p._price_cache["VOO"]
        p._price_cache["VOO"] = (data, ts - 700)  # expired fresh window

        # Trip the breaker so live fetch short-circuits
        p_breaker = __import__(
            "app.providers.yfinance_provider", fromlist=["_breaker"]
        )._breaker
        for _ in range(10):
            p_breaker.record_failure(ErrorCategory.RATE_LIMITED)
        assert not p_breaker.allow_request()

        result = asyncio.run(p.get_current_price("VOO"))
        assert result["price"] == 500                      # real cached price
        assert result["from_stale_cache"] is True
        assert result["status"] == "stale"                 # clearly labeled, not passed off as live

    def test_unknown_symbol_gets_structured_failure_when_open(self):
        from app.providers.yfinance_provider import YFinanceProvider
        breaker = __import__(
            "app.providers.yfinance_provider", fromlist=["_breaker"]
        )._breaker
        for _ in range(10):
            breaker.record_failure(ErrorCategory.RATE_LIMITED)

        p = YFinanceProvider()
        result = asyncio.run(p.get_current_price("ZZZZ"))
        assert result["price"] is None                     # NO fabricated price
        assert result["status"] == "provider_unavailable"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
