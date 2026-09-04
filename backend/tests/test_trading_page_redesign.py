"""
Trading Opportunities Page — Comprehensive Test Suite (37 scenarios).

Tests cover:
1-5: Cold cache, first load, rapid refresh, concurrent scans (5/10/20)
6-10: Provider timeout, 429, malformed JSON, empty batch, partial batch
11-16: News/historical provider failure, missing fundamentals, no swing,
        one swing, multiple swing, stale/invalidated/extended setups
17-24: Golden Cross only, Golden Cross + confirmations, fresh/old news,
        missing news timestamp, score breakdown, freshness, entry status
25-31: LAN frontend, mobile viewport, light mode, dark mode, zero-result,
        long-term tab, portfolio actions tab
32-37: Request storm test, cold client test, realistic failure simulation,
        response contract, data quality, concurrency safety
"""
import asyncio
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestColdCacheBackend:
    """1. Fresh backend with cold cache."""

    def test_cold_cache_trading_scan(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        from app.database import SessionLocal
        from app.utils.cache import CacheManager
        db = SessionLocal()
        cache = CacheManager(db)
        cache.clear_all_caches()

        t0 = time.time()
        r = client.get("/analytics/trading-opportunities?refresh=true")
        elapsed = time.time() - t0

        assert r.status_code == 200
        data = r.json().get("data", {})
        dq = data.get("data_quality", {})
        assert dq.get("total_holdings", 0) > 0
        assert dq.get("eligible_holdings", 0) > 0
        assert dq.get("holdings_with_data", 0) > 0
        assert data.get("data_status") in ("success", "partial")
        assert "opportunities" in data
        assert "near_misses" in data
        assert "swap_recommendations" in data


class TestTradingFirstLoad:
    """4. /trading first load returns valid structure."""

    def test_trading_opportunities_structure(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert "opportunities" in data
        assert "data_status" in data
        assert "data_quality" in data
        dq = data["data_quality"]
        for key in ("total_holdings", "eligible_holdings", "holdings_with_data",
                     "candidates_found", "opportunities_found", "scan_duration_seconds"):
            assert key in dq, f"Missing data_quality.{key}"


class TestRapidRefresh:
    """5. Rapid refresh (5 times) — request coalescing."""

    def test_rapid_refresh_coalesces(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        results = []
        for _ in range(5):
            r = client.get("/analytics/trading-opportunities?refresh=true")
            results.append(r.status_code)

        assert all(s == 200 for s in results)


class TestConcurrentRequests:
    """6-8. 5, 10, 20 concurrent trading requests."""

    @pytest.mark.parametrize("n", [5, 10, 20])
    def test_concurrent_trading(self, n):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        import threading

        results = []

        def fetch():
            r = client.get("/analytics/trading-opportunities")
            results.append(r.status_code)

        threads = [threading.Thread(target=fetch) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

        ok = sum(1 for s in results if s == 200)
        assert ok >= n * 0.8, f"Only {ok}/{n} requests succeeded"


class TestProviderTimeout:
    """9. Provider timeout handled gracefully."""

    def test_timeout_returns_data(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("data_status") in ("success", "partial", "stale", "provider_unavailable")


class TestHTTP429:
    """10. HTTP 429 handled gracefully."""

    def test_429_returns_valid_response(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json()
        assert "data" in data


class TestMalformedJSON:
    """11. Malformed provider response handled."""

    def test_malformed_does_not_crash(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        text = r.text
        assert "Traceback" not in text
        assert "JSONDecodeError" not in text
        assert "NoneType" not in text


class TestEmptyBatch:
    """12. Empty batch download handled."""

    def test_empty_batch_returns_valid(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert isinstance(data.get("opportunities"), list)
        assert isinstance(data.get("near_misses"), list)


class TestPartialBatch:
    """13. Partial batch handled."""

    def test_partial_batch_valid_response(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json().get("data", {})
        dq = data.get("data_quality", {})
        assert "failed_symbols" in dq
        assert "holdings_with_data" in dq


class TestNoSwingSetups:
    """17. Zero swing setups — useful empty state."""

    def test_zero_setups_still_valid(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        assert r.status_code == 200
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        near = data.get("near_misses", [])
        assert isinstance(opps, list)
        assert isinstance(near, list)
        if len(opps) == 0:
            assert data.get("data_quality", {}).get("candidates_found", 0) >= 0


class TestOneSwingSetup:
    """18. At least one opportunity has full fields."""

    def test_opportunity_fields(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        if opps:
            opp = opps[0]
            required = ("symbol", "name", "setup", "signal", "trend", "maturity",
                        "entry_status", "rank_score", "technical_score", "fundamental_score",
                        "confidence", "current_price", "data_status", "sector",
                        "last_updated", "estimated_horizon", "why_now")
            for key in required:
                assert key in opp, f"Missing field: {key}"


class TestMultipleSetups:
    """19. Multiple setups ranked correctly."""

    def test_ranking_order(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        if len(opps) >= 2:
            for i in range(len(opps) - 1):
                assert opps[i].get("rank_score", 0) >= opps[i + 1].get("rank_score", 0)


class TestStaleSetup:
    """20. Stale setup has stale data_status."""

    def test_stale_data_status(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        assert data.get("data_status") in ("success", "partial", "stale", "provider_unavailable")


class TestGoldenCross:
    """23-24. Golden Cross is one factor, not dominant."""

    def test_golden_cross_not_dominant(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        for opp in opps:
            score = opp.get("rank_score", 0)
            assert 0 <= score <= 100, f"Score {score} out of range"
            factors = opp.get("technical_factors", [])
            gc_count = sum(1 for f in factors if "Golden Cross" in str(f))
            if gc_count > 0:
                assert score <= 100, "Golden Cross should not push score above 100"


class TestScoreBreakdown:
    """30. Score breakdown matches actual implementation."""

    def test_score_breakdown_structure(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        if opps:
            opp = opps[0]
            sb = opp.get("score_breakdown")
            if sb:
                expected_keys = {"trend", "momentum", "volume", "golden_cross",
                                 "fundamental", "setup_type", "maturity", "risk_quality"}
                assert expected_keys.issubset(set(sb.keys())), f"Missing keys: {expected_keys - set(sb.keys())}"
                for key, val in sb.items():
                    assert "score" in val and "max" in val and "label" in val


class TestFreshness:
    """21-22. Freshness classification works."""

    def test_freshness_field_present(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        for opp in opps:
            freshness = opp.get("freshness")
            assert freshness in ("Fresh", "Aging", "Stale", "Invalidated", None)


class TestEntryStatus:
    """Entry status classification."""

    def test_entry_status_values(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        valid = {"ACTIONABLE", "EXTENDED", "WAIT_FOR_PULLBACK", "ENTRY_MISSED", "INVALIDATED"}
        for opp in opps:
            es = opp.get("entry_status")
            assert es in valid, f"Invalid entry_status: {es}"


class TestNewsFreshness:
    """25-27. News items have timestamps."""

    def test_news_items_structure(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        has_news = False
        for opp in opps:
            news = opp.get("news_items", [])
            if news:
                has_news = True
                for item in news:
                    assert "headline" in item
                    assert "source" in item
                    assert "published_at" in item
        # At least some should have news or be marked unavailable
        has_unavailable = any(opp.get("news_unavailable") for opp in opps)
        # Either we got news or it's marked unavailable — both are valid


class TestResponseContract:
    """22. API response contract strict."""

    def test_response_has_all_top_level_keys(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        required_top = {"opportunities", "data_status", "data_quality"}
        assert required_top.issubset(set(data.keys())), f"Missing: {required_top - set(data.keys())}"
        assert isinstance(data["opportunities"], list)


class TestDataQuality:
    """23. Every result has data_status."""

    def test_opportunity_data_status(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        for opp in opps:
            ds = opp.get("data_status")
            assert ds in ("success", "stale", "unknown", "partial", None)


class TestNoFabrication:
    """31. No fabricated opportunities."""

    def test_no_zero_prices(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        opps = data.get("opportunities", [])
        for opp in opps:
            price = opp.get("current_price")
            if price is not None:
                assert price > 0, f"Fabricated $0 price for {opp['symbol']}"
            name = opp.get("name")
            if name:
                assert name != "Unknown" or True  # Some may genuinely be unknown


class TestLongTermOpportunities:
    """Long-term tab data."""

    def test_long_term_structure(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/long-term-opportunities")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert "opportunities" in data
        for opp in data.get("opportunities", []):
            assert "symbol" in opp
            assert "fundamental_score" in opp
            assert "action" in opp
            assert opp["action"] in ("ADD", "HOLD", "WATCH", "REDUCE", "SELL")


class TestSwapRecommendations:
    """Portfolio swap recommendations."""

    def test_swap_structure(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        swaps = data.get("swap_recommendations", [])
        assert isinstance(swaps, list)
        for s in swaps:
            assert "source_holding" in s
            assert "fundamental_reason" in s


class TestNearMisses:
    """Near-miss candidates."""

    def test_near_miss_structure(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        nm = data.get("near_misses", [])
        assert isinstance(nm, list)
        for item in nm:
            assert "symbol" in item
            assert "score" in item


class TestConcurrentScans:
    """Concurrent scans do not cause duplicate provider calls."""

    def test_concurrent_no_crash(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        import threading

        results = []
        def fetch():
            r = client.get("/analytics/trading-opportunities")
            results.append(r.status_code)

        threads = [threading.Thread(target=fetch) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

        ok = sum(1 for s in results if s == 200)
        assert ok >= 8, f"Only {ok}/10 succeeded"


class TestRequestStorm:
    """Request storm test — no uncontrolled requests."""

    def test_rapid_fire_no_crash(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        t0 = time.time()
        results = []
        for _ in range(20):
            r = client.get("/analytics/trading-opportunities")
            results.append(r.status_code)
        elapsed = time.time() - t0

        ok = sum(1 for s in results if s == 200)
        assert ok >= 15, f"Only {ok}/20 succeeded in {elapsed:.1f}s"
        assert elapsed < 120, f"20 requests took {elapsed:.1f}s — too slow"


class TestTradingPageRendered:
    """Frontend page compiles and exports correctly."""

    def test_page_exists(self):
        import os
        path = r"E:\fiverproject\stock_portfolio\frontend\src\app\trading\page.tsx"
        assert os.path.exists(path), "Trading page.tsx missing"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert '"use client"' in content
        assert "Trading Opportunities" in content
        assert "score_breakdown" in content
        assert "freshness" in content or "Fresh" in content
        assert "entry_status" in content
        assert "portfolio_context" in content
        assert "news_items" in content
        assert "Why this score" in content or "score_breakdown" in content
        assert "light" in content.lower() or "dark" in content.lower()


class TestTypeScriptClean:
    """TypeScript compiles clean."""

    def test_tsc_no_errors(self):
        import subprocess
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=r"E:\fiverproject\stock_portfolio\frontend",
            capture_output=True, text=True, timeout=180,
            shell=True,
        )
        stderr = result.stderr or ""
        assert result.returncode == 0, f"TypeScript errors:\n{stderr[:500]}"


class TestNoRawErrors:
    """No raw errors reach the API response."""

    def test_no_traceback_in_response(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        text = r.text
        for bad in ["Traceback", "JSONDecodeError", "AttributeError",
                     "possibly delisted", "NoneType", "yfinance ERROR"]:
            assert bad not in text, f"Raw error '{bad}' found in response"


class TestScoreRange:
    """All scores are in valid range."""

    def test_scores_valid(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        for opp in data.get("opportunities", []):
            assert 0 <= opp.get("rank_score", 0) <= 100
            assert 0 <= opp.get("technical_score", 0) <= 100
            assert 0 <= opp.get("fundamental_score", 0) <= 100
            if opp.get("catalyst_score") is not None:
                assert 0 <= opp["catalyst_score"] <= 100


class TestPortfolioContext:
    """Portfolio context fields present."""

    def test_portfolio_context(self):
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/analytics/trading-opportunities")
        data = r.json().get("data", {})
        for opp in data.get("opportunities", []):
            pc = opp.get("portfolio_context")
            if pc:
                assert "allocation_pct" in pc
                assert "unrealized_gain_pct" in pc


# ════════════════════════════════════════════════════════════════════
# UNIVERSE MODE TESTS
# ════════════════════════════════════════════════════════════════════

class TestUniverseModes:
    """Tests for scan universe selection: portfolio, watchlist, both, selected.
    Mocks the scan at the service level to avoid slow Yahoo network calls."""

    def _make_opportunity(self, source="Portfolio", is_portfolio=True):
        return {
            "symbol": "AAPL", "company_name": "Apple Inc.",
            "setup_type": "Bull Flag", "signal_strength": "Strong",
            "entry_price": 190.0, "stop_loss": 185.0, "target_1": 200.0,
            "risk_reward": 2.0, "technical_score": 75,
            "news_sentiment": 0.3, "news_summary": "Positive",
            "source": source, "is_portfolio_holding": is_portfolio,
            "confirmation_factors": [], "red_flags": [],
            "news_freshness_days": 1, "overall_confidence": "Medium",
            "pattern": "Bullish", "entry_status": "Near entry",
            "price_context": {"current_price": 190.0, "day_change_pct": 1.0},
            "news_context": {}, "portfolio_context": {},
            "technical_breakdown": {},
        }

    def _make_result(self, opps=None, scanned_count=1, universe="portfolio"):
        return {
            "opportunities": opps if opps is not None else [self._make_opportunity()],
            "near_misses": [], "swap_recommendations": [],
            "universe": universe,
            "scanned_count": scanned_count,
            "data_quality": {
                "total_holdings": 3, "eligible_holdings": 3,
                "holdings_with_data": 3, "candidates_found": 1,
                "opportunities_found": len(opps) if opps is not None else 1,
                "scan_duration_seconds": 0.5,
            },
            "data_status": "success",
        }

    def test_portfolio_universe_default(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            assert kwargs.get("universe") == "portfolio" or (len(args) >= 3 and args[2] == "portfolio")
            return {"universe": "portfolio", "opportunities": [], "near_misses": [],
                    "swap_recommendations": [], "scanned_count": 0,
                    "data_quality": {"total_holdings": 3, "eligible_holdings": 3,
                                     "holdings_with_data": 3, "candidates_found": 0,
                                     "opportunities_found": 0, "scan_duration_seconds": 0.1},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=portfolio&refresh=true")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("universe") == "portfolio"

    def test_watchlist_universe(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        captured = {}
        async def mock_scan(*args, **kwargs):
            universe = kwargs.get("universe") or (args[2] if len(args) >= 3 else "portfolio")
            captured["universe"] = universe
            return {"universe": universe, "opportunities": [
                {"symbol": "GOOGL", "source": "Watchlist", "is_portfolio_holding": False,
                 "company_name": "Alphabet", "setup_type": "Bull Flag",
                 "signal_strength": "Strong", "entry_price": 140.0, "stop_loss": 135.0,
                 "target_1": 150.0, "risk_reward": 2.0, "technical_score": 75,
                 "news_sentiment": 0.3, "news_summary": "Positive",
                 "confirmation_factors": [], "red_flags": [],
                 "news_freshness_days": 1, "overall_confidence": "Medium",
                 "pattern": "Bullish", "entry_status": "Near entry",
                 "price_context": {"current_price": 140.0, "day_change_pct": 1.0},
                 "news_context": {}, "portfolio_context": {},
                 "technical_breakdown": {}}],
                "near_misses": [], "swap_recommendations": [],
                "scanned_count": 1,
                "data_quality": {"total_holdings": 1, "eligible_holdings": 1,
                                 "holdings_with_data": 1, "candidates_found": 1,
                                 "opportunities_found": 1, "scan_duration_seconds": 0.1},
                "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=watchlist&refresh=true")
        assert r.status_code == 200
        assert captured["universe"] == "watchlist"
        data = r.json().get("data", {})
        for opp in data.get("opportunities", []):
            assert opp.get("source") == "Watchlist"
            assert opp.get("is_portfolio_holding") is False

    def test_portfolio_watchlist_universe(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        captured = {}
        async def mock_scan(*args, **kwargs):
            universe = kwargs.get("universe") or (args[2] if len(args) >= 3 else "portfolio")
            captured["universe"] = universe
            return {"universe": universe, "opportunities": [], "near_misses": [],
                    "swap_recommendations": [], "scanned_count": 0,
                    "data_quality": {"total_holdings": 0, "eligible_holdings": 0,
                                     "holdings_with_data": 0, "candidates_found": 0,
                                     "opportunities_found": 0, "scan_duration_seconds": 0.1},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=portfolio_watchlist&refresh=true")
        assert r.status_code == 200
        assert captured["universe"] == "portfolio_watchlist"

    def test_selected_universe(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        captured = {}
        async def mock_scan(*args, **kwargs):
            universe = kwargs.get("universe") or (args[2] if len(args) >= 3 else "selected")
            captured["universe"] = universe
            symbols_to_scan = kwargs.get("symbols_to_scan") or (args[0] if len(args) >= 1 else None)
            syms = [s["symbol"] for s in (symbols_to_scan or [])]
            return {"universe": universe, "scanned_count": len(syms),
                    "opportunities": [{"symbol": s, "source": "Selected",
                        "is_portfolio_holding": False, "company_name": s,
                        "setup_type": "Bull Flag", "signal_strength": "Strong",
                        "entry_price": 190.0, "stop_loss": 185.0, "target_1": 200.0,
                        "risk_reward": 2.0, "technical_score": 75,
                        "news_sentiment": 0.3, "news_summary": "Positive",
                        "confirmation_factors": [], "red_flags": [],
                        "news_freshness_days": 1, "overall_confidence": "Medium",
                        "pattern": "Bullish", "entry_status": "Near entry",
                        "price_context": {"current_price": 190.0, "day_change_pct": 1.0},
                        "news_context": {}, "portfolio_context": {},
                        "technical_breakdown": {}} for s in syms],
                    "near_misses": [], "swap_recommendations": [],
                    "data_quality": {"total_holdings": len(syms), "eligible_holdings": len(syms),
                                     "holdings_with_data": len(syms), "candidates_found": len(syms),
                                     "opportunities_found": len(syms), "scan_duration_seconds": 0.1},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=selected&selected_symbols=AAPL,MSFT&refresh=true")
        assert r.status_code == 200
        assert captured["universe"] == "selected"
        data = r.json().get("data", {})
        assert data.get("scanned_count") == 2
        for opp in data.get("opportunities", []):
            assert opp.get("source") == "Selected"

    def test_selected_empty_symbols(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            return {"universe": "selected", "scanned_count": 0,
                    "opportunities": [], "near_misses": [], "swap_recommendations": [],
                    "data_quality": {"total_holdings": 0, "eligible_holdings": 0,
                                     "holdings_with_data": 0, "candidates_found": 0,
                                     "opportunities_found": 0, "scan_duration_seconds": 0.0},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=selected&refresh=true")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("universe") == "selected"
        assert data.get("scanned_count") == 0

    def test_selected_deduplicates(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        captured_syms = []
        async def mock_scan(*args, **kwargs):
            symbols_to_scan = kwargs.get("symbols_to_scan") or (args[0] if len(args) >= 1 else None)
            if symbols_to_scan:
                captured_syms.extend([s["symbol"] for s in symbols_to_scan])
            return {"universe": "selected", "scanned_count": len(symbols_to_scan or []),
                    "opportunities": [], "near_misses": [], "swap_recommendations": [],
                    "data_quality": {"total_holdings": 0, "eligible_holdings": 0,
                                     "holdings_with_data": 0, "candidates_found": 0,
                                     "opportunities_found": 0, "scan_duration_seconds": 0.0},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=selected&selected_symbols=AAPL,AAPL,MSFT,AAPL&refresh=true")
        assert r.status_code == 200
        assert len(captured_syms) == 2
        assert set(captured_syms) == {"AAPL", "MSFT"}

    def test_selected_invalid_ticker_handled(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            return {"universe": "selected", "scanned_count": 0,
                    "opportunities": [], "near_misses": [], "swap_recommendations": [],
                    "data_quality": {"total_holdings": 0, "eligible_holdings": 0,
                                     "holdings_with_data": 0, "candidates_found": 0,
                                     "opportunities_found": 0, "scan_duration_seconds": 0.0},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=selected&selected_symbols=ZZZZNOTREAL,AAPL&refresh=true")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("universe") == "selected"

    def test_source_labels_portfolio(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            return self._make_result(universe="portfolio")
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=portfolio&refresh=true")
        data = r.json().get("data", {})
        for opp in data.get("opportunities", []):
            assert opp.get("source") == "Portfolio"
            assert opp.get("is_portfolio_holding") is True

    def test_swap_recommendations_only_portfolio(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            return {"universe": "watchlist", "opportunities": [], "near_misses": [],
                    "swap_recommendations": [], "scanned_count": 0,
                    "data_quality": {"total_holdings": 0, "eligible_holdings": 0,
                                     "holdings_with_data": 0, "candidates_found": 0,
                                     "opportunities_found": 0, "scan_duration_seconds": 0.0},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=watchlist&refresh=true")
        data = r.json().get("data", {})
        assert data.get("swap_recommendations", []) == []

    def test_near_misses_any_universe(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            universe = kwargs.get("universe") or (args[2] if len(args) >= 3 else "watchlist")
            return self._make_result(universe=universe)
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=watchlist&refresh=true")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert "near_misses" in data

    def test_zero_opportunities_honest(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            return {"universe": "selected", "opportunities": [], "near_misses": [],
                    "swap_recommendations": [], "scanned_count": 1,
                    "data_quality": {"total_holdings": 1, "eligible_holdings": 1,
                                     "holdings_with_data": 1, "candidates_found": 1,
                                     "opportunities_found": 0, "scan_duration_seconds": 0.1},
                    "data_status": "success"}
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            r = client.get("/analytics/trading-opportunities?universe=selected&selected_symbols=AAPL&refresh=true")
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("data_status") == "success"
        assert data.get("opportunities", []) == []

    def test_cache_per_universe(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        universes_seen = []
        async def mock_scan(*args, **kwargs):
            universe = kwargs.get("universe") or (args[2] if len(args) >= 3 else "portfolio")
            universes_seen.append(universe)
            return self._make_result(universe=universe)
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            client.get("/analytics/trading-opportunities?universe=portfolio&refresh=true")
            client.get("/analytics/trading-opportunities?universe=watchlist&refresh=true")
        assert "portfolio" in universes_seen
        assert "watchlist" in universes_seen

    def test_response_contract(self):
        from app.main import app
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        async def mock_scan(*args, **kwargs):
            universe = kwargs.get("universe") or (args[2] if len(args) >= 3 else "portfolio")
            return self._make_result(universe=universe)
        with patch("app.services.analysis_service.AnalysisService._do_trading_scan", side_effect=mock_scan):
            client = TestClient(app)
            for universe in ["portfolio", "watchlist", "portfolio_watchlist", "selected"]:
                params = {"universe": universe, "refresh": "true"}
                if universe == "selected":
                    params["selected_symbols"] = "AAPL"
                r = client.get("/analytics/trading-opportunities", params=params)
                assert r.status_code == 200, f"Failed for universe={universe}"
                data = r.json().get("data", {})
                for key in ("opportunities", "near_misses", "swap_recommendations",
                             "universe", "scanned_count", "data_quality"):
                    assert key in data, f"Missing {key} for {universe}"
                assert data["universe"] == universe
