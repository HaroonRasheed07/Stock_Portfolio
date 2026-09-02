"""
Simple test without scipy import to check engine core.
"""
import pytest
from app.utils.csv_parser import parse_csv_content, _clean_number
from app.engines.technical import TechnicalEngine
from app.engines.recommendation import RecommendationEngine


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
