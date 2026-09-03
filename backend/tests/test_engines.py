"""
Simple test without scipy import to check engine core.
"""
import pytest
from app.utils.csv_parser import parse_csv_content, _clean_number
from app.engines.technical import TechnicalEngine
from app.engines.recommendation import RecommendationEngine
from app.engines.fundamental import FundamentalEngine
from app.services.stock_service import StockService


def test_clean_number():
    assert _clean_number("$1,234.56") == 1234.56
    assert _clean_number("(1,234.56)") == -1234.56
    assert _clean_number("80.71%") == 80.71
    assert _clean_number("-") is None


def test_parse_csv_content():
    sample_csv = """Symbol,Name,Quantity,Avg. Price,Cost Basis,Unrealized Gain ($),Unrealized Gain (%),Value
VOO,Vanguard S&P 500 ETF,14.83,394.90,"5,857.99","4,727.81",80.71,"10,585.80"
JPM,JPMorgan Chase & Co.,20.05,145.54,"2,919.15","4,358.55",149.31,"7,277.70"
MICC,The Magnum Ice Cream Company N.V.,12.53,,,,,245.51
"""
    result = parse_csv_content(sample_csv)
    assert result["total_rows"] == 3
    assert result["valid_rows"] == 3
    assert result["estimated_total_value"] > 0


def test_recommendation_engine():
    engine = RecommendationEngine()
    rec = engine.recommend(
        symbol="AAPL",
        fundamental_score=85,
        fundamental_data={"score": 85, "metrics": {"pe_ratio": 22}},
        technical_data={"trend": "Uptrend", "trend_strength": 75, "momentum": "Bullish"},
        risk_data={"risk_score": 35},
        sentiment_data={"overall_score": 0.4, "overall_sentiment": "Positive"},
        risk_profile="moderate",
    )
    assert rec["recommendation"] in ("BUY", "HOLD", "WATCH")
    assert len(rec["reasons"]) > 0
    assert "anti_panic_note" in rec
    assert "positive_factors" in rec
    assert "negative_factors" in rec
    assert "what_would_change" in rec


def test_fundamental_neutral_when_no_data():
    """When Yahoo info is blocked (empty), the score should be a neutral 50,
    NOT 0, so it is never mistaken for a poor-quality assessment."""
    result = FundamentalEngine().analyze({})
    assert result["score"] == 50
    assert result["grade"] == "Insufficient Data"
    assert "neutral" in result["explanation"].lower()


def test_fundamental_neutral_when_too_few_metrics():
    """Known company with only a name (Render fallback) but no live metrics
    yields a neutral 50, named explicitly, not a misleading 0."""
    result = FundamentalEngine().analyze({"symbol": "AAPL", "name": "Apple Inc."})
    assert result["score"] == 50
    assert result["grade"] == "Insufficient Data"
    assert "Apple Inc." in result["explanation"]


def test_fundamental_full_data_still_scores():
    """Normal scoring must be unchanged when real metrics are available."""
    full = {
        "symbol": "AAPL", "name": "Apple Inc.",
        "revenue_growth": 0.10, "pe_ratio": 37.3, "beta": 1.08,
        "market_cap": 3.0e12, "eps": 8.71,
    }
    result = FundamentalEngine().analyze(full)
    assert result["score"] >= 40
    assert result["grade"] in ("Strong", "Healthy", "Mixed")


def test_stock_info_completeness_guard():
    """A name-only (partial/blocked) stock-info result must NOT be cached as if
    complete; only results with real company content are considered cachable."""
    assert not StockService._info_has_company_data({})
    assert not StockService._info_has_company_data({"name": "NVIDIA Corporation"})
    assert not StockService._info_has_company_data({"name": "X", "pe_ratio": None, "eps": None})
    assert StockService._info_has_company_data({"name": "X", "description": "A tech company."})
    assert StockService._info_has_company_data({"name": "X", "market_cap": 2_000_000_000_000})
    assert StockService._info_has_company_data({"name": "X", "eps": 8.71})
