"""
Sentiment analysis engine using VADER and TextBlob.
Free, local, no API required.
"""
import logging
from typing import Dict, Any, List, Optional
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

# High-impact financial keywords
HIGH_IMPACT_KEYWORDS = {
    "earnings", "revenue", "profit", "loss", "bankruptcy", "acquisition",
    "merger", "fda", "approval", "lawsuit", "sec", "investigation",
    "guidance", "forecast", "dividend", "layoff", "restructuring",
    "ipo", "buyback", "split", "recall", "default", "downgrade",
    "upgrade", "beat", "miss", "warning", "settlement",
}

MEDIUM_IMPACT_KEYWORDS = {
    "analyst", "target", "rating", "outlook", "expansion", "partnership",
    "contract", "launch", "product", "ceo", "cfo", "board", "hire",
    "quarterly", "annual", "report", "growth", "decline", "market",
    "sector", "industry", "regulation", "policy", "inflation", "rate",
}


class SentimentEngine:
    """Analyzes text sentiment using VADER (optimized for financial text)."""

    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of a single text string."""
        if not text:
            return {"score": 0.0, "label": "neutral", "impact": "low"}

        scores = self.analyzer.polarity_scores(text)
        compound = scores["compound"]

        # Classify sentiment
        if compound >= 0.2:
            label = "positive"
        elif compound <= -0.2:
            label = "negative"
        else:
            label = "neutral"

        # Determine impact based on keywords
        text_lower = text.lower()
        impact = "low"
        for keyword in HIGH_IMPACT_KEYWORDS:
            if keyword in text_lower:
                impact = "high"
                break
        if impact == "low":
            for keyword in MEDIUM_IMPACT_KEYWORDS:
                if keyword in text_lower:
                    impact = "medium"
                    break

        return {
            "score": round(compound, 3),
            "label": label,
            "impact": impact,
            "positive": round(scores["pos"], 3),
            "negative": round(scores["neg"], 3),
            "neutral": round(scores["neu"], 3),
        }

    def analyze_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze sentiment across multiple news articles with time-weighted scoring."""
        if not articles:
            return {
                "overall_score": 0.0,
                "overall_sentiment": "Neutral",
                "positive_count": 0,
                "neutral_count": 0,
                "negative_count": 0,
            }

        positive_count = 0
        neutral_count = 0
        negative_count = 0
        weighted_scores = []

        for i, article in enumerate(articles):
            title = article.get("title", "")
            summary = article.get("summary", "")
            text = f"{title}. {summary}" if summary else title

            sentiment = self.analyze_text(text)

            # Time weight: more recent articles have higher weight
            # Assume articles are sorted newest first
            weight = 1.0 / (1.0 + i * 0.1)
            weighted_scores.append(sentiment["score"] * weight)

            if sentiment["label"] == "positive":
                positive_count += 1
            elif sentiment["label"] == "negative":
                negative_count += 1
            else:
                neutral_count += 1

        # Weighted average
        total_weight = sum(1.0 / (1.0 + i * 0.1) for i in range(len(articles)))
        overall_score = sum(weighted_scores) / total_weight if total_weight > 0 else 0

        if overall_score >= 0.15:
            overall_sentiment = "Positive"
        elif overall_score <= -0.15:
            overall_sentiment = "Negative"
        else:
            overall_sentiment = "Neutral"

        return {
            "overall_score": round(overall_score, 3),
            "overall_sentiment": overall_sentiment,
            "positive_count": positive_count,
            "neutral_count": neutral_count,
            "negative_count": negative_count,
        }
