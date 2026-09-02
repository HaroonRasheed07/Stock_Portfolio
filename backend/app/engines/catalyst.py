"""
Advanced Catalyst Detection & Classification Engine.
Identifies, classifies, and scores market-moving events from multiple data sources.
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Catalyst Type Definitions ──────────────────────────────

CATALYST_TYPES = {
    "clinical_trial": {
        "category": "biotech_pharma",
        "base_impact": "HIGH",
        "keywords": [
            "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii",
            "clinical trial", "trial result", "trial data", "trial endpoint",
            "primary endpoint", "secondary endpoint", "interim analysis",
            "data readout", "pivotal trial", " registrational",
        ],
        "high_severity_keywords": [
            "phase 3", "phase iii", "pivotal", "registrational", "primary endpoint met",
            "failed to meet", "missed endpoint", "terminated", "discontinued",
            "breakthrough", "accelerated approval",
        ],
        "negative_keywords": [
            "failed", "missed", "terminated", "discontinued", "adverse event",
            "safety signal", "complete response letter", "clinical hold",
        ],
    },
    "fda_approval": {
        "category": "biotech_pharma",
        "base_impact": "CRITICAL",
        "keywords": [
            "fda approval", "fda approves", "fda clears", "fda authorization",
            "ema approval", "regulatory approval", "drug approval",
            "marketing authorization", "accelerated approval",
            "full approval", "supplemental approval",
        ],
        "high_severity_keywords": [
            "fda approval", "full approval", "marketing authorization",
        ],
        "negative_keywords": [
            "complete response letter", "fda rejects", "fda refusal",
            "not approved", "approvable letter", "clinical hold",
        ],
    },
    "fda_rejection": {
        "category": "biotech_pharma",
        "base_impact": "CRITICAL",
        "keywords": [
            "complete response letter", "crl", "fda rejects", "fda refuses",
            "not approved", "approvable letter", "clinical hold",
            "fda issues", "regulatory setback",
        ],
        "high_severity_keywords": ["complete response letter", "crl"],
        "negative_keywords": ["complete response letter", "rejects", "refuses"],
    },
    "earnings_release": {
        "category": "financial",
        "base_impact": "HIGH",
        "keywords": [
            "earnings", "quarterly results", "q1 results", "q2 results",
            "q3 results", "q4 results", "annual results", "fiscal year",
            "eps beat", "eps miss", "revenue beat", "revenue miss",
            "earnings report", "financial results",
        ],
        "high_severity_keywords": [
            "record revenue", "record earnings", "guidance raised",
            "guidance lowered", "beat expectations", "missed expectations",
            "surprise", "blowout", "disappointing",
        ],
        "negative_keywords": [
            "miss", "missed", "disappointing", "shortfall", "below expectations",
            "weak guidance", "lowered guidance", "cut guidance",
        ],
    },
    "guidance_change": {
        "category": "financial",
        "base_impact": "HIGH",
        "keywords": [
            "guidance", "outlook", "forecast", "raised guidance",
            "lowered guidance", "revised guidance", "updated outlook",
            "forward guidance", "full year guidance",
        ],
        "high_severity_keywords": [
            "raised guidance", "lowered guidance", "cut guidance",
            "significantly raised", "significantly lowered",
        ],
        "negative_keywords": [
            "lowered", "cut", "reduced", "below", "weaker",
        ],
    },
    "merger_acquisition": {
        "category": "corporate",
        "base_impact": "CRITICAL",
        "keywords": [
            "acquisition", "merger", "acquire", "acquired", "buyout",
            "takeover", "deal", "definitive agreement", "tender offer",
            "take-private", "goes private",
        ],
        "high_severity_keywords": [
            "definitive agreement", "tender offer", "take-private",
            "all-stock deal", "all-cash deal", "unsolicited",
        ],
        "negative_keywords": [
            "rejected", "hostile", "withdrawn", "regulatory block",
        ],
    },
    "major_contract": {
        "category": "corporate",
        "base_impact": "HIGH",
        "keywords": [
            "contract", "partnership", "agreement", "supply deal",
            "government contract", "defense contract", "major order",
            "strategic partnership", "collaboration",
        ],
        "high_severity_keywords": [
            "billion", "multi-year", "government contract", "defense",
            "exclusive", "landmark",
        ],
        "negative_keywords": [
            "lost contract", "terminated", "expired", "cancelled",
        ],
    },
    "product_launch": {
        "category": "corporate",
        "base_impact": "MEDIUM",
        "keywords": [
            "product launch", "new product", "unveil", "introduce",
            "release", "debut", "new service", "expansion",
            "market launch", "commercial launch",
        ],
        "high_severity_keywords": [
            "flagship", "first-of-its-kind", "breakthrough",
            "industry first", "disruptive",
        ],
        "negative_keywords": [
            "delayed", "postponed", "recalled", "discontinued",
        ],
    },
    "insider_activity": {
        "category": "corporate",
        "base_impact": "MEDIUM",
        "keywords": [
            "insider buying", "insider selling", "ceo buys", "ceo sells",
            "cfo buys", "cfo sells", "insider transaction", "form 4",
            "10b5-1", "insider purchase", "insider sale",
        ],
        "high_severity_keywords": [
            "ceo buys", "large purchase", "significant buying",
            "cluster buying", "multiple insiders",
        ],
        "negative_keywords": [
            "insider selling", "ceo sells", "cfo sells", "large sale",
            "significant selling",
        ],
    },
    "management_change": {
        "category": "corporate",
        "base_impact": "MEDIUM",
        "keywords": [
            "ceo", "cfo", "cto", "coo", "resign", "appoint",
            "hire", "board", "executive", "leadership change",
            "chief executive", "chief financial", "successor",
        ],
        "high_severity_keywords": [
            "ceo resigns", "ceo steps down", "ceo fired",
            "abrupt departure", "leadership crisis",
        ],
        "negative_keywords": [
            "resign", "steps down", "fired", "terminated", "departed",
        ],
    },
    "analyst_action": {
        "category": "market_opinion",
        "base_impact": "MEDIUM",
        "keywords": [
            "upgrade", "downgrade", "price target", "analyst",
            "rating", "initiate", "initiation", "overweight",
            "underweight", "outperform", "underperform",
            "buy rating", "sell rating", "hold rating",
        ],
        "high_severity_keywords": [
            "double upgrade", "double downgrade", "massive price target",
            "sector upgrade", "sector downgrade",
        ],
        "negative_keywords": [
            "downgrade", "underweight", "underperform", "sell",
            "reduce", "negative",
        ],
    },
    "regulatory_investigation": {
        "category": "legal_regulatory",
        "base_impact": "HIGH",
        "keywords": [
            "sec investigation", "doj investigation", "antitrust",
            "subpoena", "warrant", "indictment", "fraud",
            "regulatory investigation", "government probe",
            "class action", "lawsuit filed",
        ],
        "high_severity_keywords": [
            "sec investigation", "doj", "indictment", "criminal",
            "fraud charges", "securities fraud",
        ],
        "negative_keywords": [
            "investigation", "probe", "subpoena", "lawsuit",
            "indictment", "charges",
        ],
    },
    "legal_development": {
        "category": "legal_regulatory",
        "base_impact": "MEDIUM",
        "keywords": [
            "settlement", "court ruling", "patent", "litigation",
            "verdict", "lawsuit", "injunction", "ruling",
            "appeal", "arbitration",
        ],
        "high_severity_keywords": [
            "settlement", "injunction", "billion dollar", "class action",
        ],
        "negative_keywords": [
            "ruled against", "lost", "damages", "penalty",
        ],
    },
    "dividend_action": {
        "category": "shareholder",
        "base_impact": "LOW",
        "keywords": [
            "dividend", "payout", "distribution", "special dividend",
            "dividend increase", "dividend cut", "dividend reduction",
            "share repurchase", "buyback",
        ],
        "high_severity_keywords": [
            "special dividend", "dividend increase", "major buyback",
            "billion buyback",
        ],
        "negative_keywords": [
            "dividend cut", "dividend reduction", "suspended dividend",
        ],
    },
    "stock_action": {
        "category": "shareholder",
        "base_impact": "MEDIUM",
        "keywords": [
            "stock split", "reverse split", "share offering",
            "secondary offering", "dilution", "convertible",
            "shelf registration", "at-the-market",
        ],
        "high_severity_keywords": [
            "stock split", "reverse split", "massive buyback",
        ],
        "negative_keywords": [
            "dilution", "secondary offering", "reverse split",
            "shelf registration",
        ],
    },
    "macro_event": {
        "category": "macroeconomic",
        "base_impact": "HIGH",
        "keywords": [
            "fed", "federal reserve", "interest rate", "rate cut",
            "rate hike", "inflation", "cpi", "gdp", "employment",
            "nonfarm", "tariff", "trade war", "recession",
            "monetary policy", "quantitative",
        ],
        "high_severity_keywords": [
            "emergency rate", "surprise rate", "aggressive rate",
            "recession", "financial crisis", "bailout",
        ],
        "negative_keywords": [
            "rate hike", "inflation surge", "recession", "crisis",
        ],
    },
    "institutional_activity": {
        "category": "market_opinion",
        "base_impact": "MEDIUM",
        "keywords": [
            "13f", "sec filing", "institutional", "hedge fund",
            "berkshire", "blackrock", "vanguard", "state street",
            "position", "stake", "accumulation",
        ],
        "high_severity_keywords": [
            "berkshire", "major stake", "accumulation", "new position",
            "significant increase",
        ],
        "negative_keywords": [
            "sold entire", "exited position", "reduced stake",
        ],
    },
}


class CatalystEngine:
    """
    Advanced catalyst detection, classification, and scoring engine.
    """

    def __init__(self):
        pass

    def _compute_content_hash(self, title: str, url: str = "") -> str:
        """Compute a hash for deduplication."""
        text = f"{title.strip().lower()}:{url.strip().lower()}"
        return hashlib.md5(text.encode()).hexdigest()

    def _match_catalyst_type(
        self, text: str
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """
        Match text against all catalyst type patterns.
        Returns list of (catalyst_type, config, confidence) sorted by confidence.
        """
        text_lower = text.lower()
        matches = []

        for cat_type, config in CATALYST_TYPES.items():
            score = 0
            matched_keywords = []

            for kw in config["keywords"]:
                if kw in text_lower:
                    score += 1
                    matched_keywords.append(kw)

            if score == 0:
                continue

            # Base confidence from keyword density
            confidence = min(0.95, 0.3 + (score * 0.15))

            # Boost for high-severity keywords
            for kw in config.get("high_severity_keywords", []):
                if kw in text_lower:
                    confidence = min(0.98, confidence + 0.15)
                    break

            # Reduce confidence for very short matches
            if len(matched_keywords) == 1 and len(text_lower) < 50:
                confidence *= 0.7

            matches.append((cat_type, config, confidence))

        # Sort by confidence descending
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches

    def _determine_sentiment(self, text: str, catalyst_type: str, config: Dict) -> Tuple[float, str]:
        """
        Determine sentiment based on catalyst type and text content.
        Returns (score, label).
        """
        text_lower = text.lower()
        negative_kws = config.get("negative_keywords", [])

        # Check for explicit negative signals
        neg_count = sum(1 for kw in negative_kws if kw in text_lower)

        # Use VADER for base sentiment
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            analyzer = SentimentIntensityAnalyzer()
            scores = analyzer.polarity_scores(text)
            compound = scores["compound"]
        except ImportError:
            compound = 0.0

        # Adjust based on catalyst-specific signals
        if neg_count > 0:
            compound -= 0.2 * neg_count

        # Catalyst-type bias
        if catalyst_type in ("fda_rejection", "regulatory_investigation"):
            compound -= 0.3
        elif catalyst_type == "fda_approval":
            compound += 0.3
        elif catalyst_type == "merger_acquisition":
            # M&A is usually positive for target, context-dependent for acquirer
            compound += 0.1

        compound = max(-1.0, min(1.0, compound))

        if compound >= 0.2:
            label = "positive"
        elif compound <= -0.2:
            label = "negative"
        else:
            label = "neutral"

        return round(compound, 3), label

    def _assess_impact(
        self,
        catalyst_type: str,
        config: Dict,
        sentiment_label: str,
        text: str,
        confidence: float,
    ) -> str:
        """
        Assess impact level: LOW, MEDIUM, HIGH, or CRITICAL.
        Based on event type, sentiment strength, and context.
        """
        base = config.get("base_impact", "MEDIUM")
        text_lower = text.lower()

        # Start with base impact
        impact = base

        # Upgrade to CRITICAL for extremely high-impact events
        if base == "HIGH":
            critical_signals = [
                "breakthrough", "landmark", "unprecedented", "first-ever",
                "billion-dollar", "blockbuster", "historical",
            ]
            if any(sig in text_lower for sig in critical_signals):
                impact = "CRITICAL"

        # Downgrade if confidence is low
        if confidence < 0.4:
            if impact == "CRITICAL":
                impact = "HIGH"
            elif impact == "HIGH":
                impact = "MEDIUM"

        # Strong negative sentiment can amplify impact for certain types
        if sentiment_label == "negative" and catalyst_type in (
            "fda_rejection", "regulatory_investigation", "earnings_release"
        ):
            if impact == "MEDIUM":
                impact = "HIGH"

        return impact

    def _generate_long_term_view(
        self, catalyst_type: str, sentiment_label: str, headline: str
    ) -> str:
        """Generate long-term investor interpretation."""
        views = {
            "clinical_trial": {
                "positive": "Positive clinical data may improve long-term product pipeline expectations. Evaluate whether the trial results materially change the probability of commercial success.",
                "negative": "Negative clinical data may impair long-term product prospects. Assess remaining pipeline and financial runway before making long-term decisions.",
                "neutral": "Clinical data reported. Evaluate trial design, endpoints, and significance before assessing long-term impact.",
            },
            "fda_approval": {
                "positive": "FDA approval enables commercialization and potential revenue generation. Evaluate market size, competition, and pricing power for long-term value.",
                "negative": "Regulatory setback may delay or prevent commercialization. Assess alternative pathways and financial impact.",
                "neutral": "Regulatory decision pending or mixed. Monitor for additional guidance.",
            },
            "earnings_release": {
                "positive": "Strong earnings may indicate improving fundamentals. Evaluate whether the trend is sustainable and reflected in valuation.",
                "negative": "Weak earnings may signal fundamental challenges. Assess whether issues are temporary or structural.",
                "neutral": "Mixed earnings results. Evaluate forward guidance and management commentary for long-term trajectory.",
            },
            "guidance_change": {
                "positive": "Raised guidance suggests improving business outlook. Consider whether the improvement is durable.",
                "negative": "Lowered guidance may indicate headwinds. Evaluate whether the cut reflects temporary or persistent factors.",
                "neutral": "Guidance updated. Monitor subsequent data points to validate the new trajectory.",
            },
            "merger_acquisition": {
                "positive": "M&A activity may unlock shareholder value. Evaluate deal terms, strategic rationale, and regulatory risks.",
                "negative": "Failed or contested deal may create uncertainty. Assess underlying business fundamentals independent of deal.",
                "neutral": "M&A news reported. Monitor deal progress and regulatory approvals.",
            },
            "major_contract": {
                "positive": "Major contract win may provide revenue visibility. Evaluate contract terms, duration, and contribution to total revenue.",
                "negative": "Contract loss or adverse terms may impact revenue. Assess diversification of revenue streams.",
                "neutral": "Contract activity reported. Evaluate strategic significance.",
            },
            "analyst_action": {
                "positive": "Analyst upgrade may reflect improving fundamentals. Consider the analyst's track record and thesis.",
                "negative": "Analyst downgrade may highlight risks. Evaluate whether the concerns are valid based on fundamentals.",
                "neutral": "Analyst opinion updated. Use as one data point among many.",
            },
        }

        type_views = views.get(catalyst_type, {})
        return type_views.get(
            sentiment_label,
            f"Event ({catalyst_type}) detected. Evaluate whether this materially changes the long-term investment thesis."
        )

    def _generate_short_term_view(
        self, catalyst_type: str, impact: str, sentiment_label: str, headline: str
    ) -> str:
        """Generate short-term trader interpretation."""
        if impact == "CRITICAL":
            prefix = "High-impact catalyst with potential for significant price movement."
        elif impact == "HIGH":
            prefix = "Notable catalyst detected that may drive short-term price action."
        elif impact == "MEDIUM":
            prefix = "Moderate catalyst that may influence near-term trading."
        else:
            prefix = "Minor event with limited expected short-term impact."

        sentiment_note = {
            "positive": "Monitor for follow-through buying and volume confirmation.",
            "negative": "Monitor for continued selling pressure and volume patterns.",
            "neutral": "Monitor price action for directional confirmation.",
        }

        return f"{prefix} {sentiment_note.get(sentiment_label, '')}"

    def _generate_potential_impact(
        self, catalyst_type: str, impact: str, sentiment_label: str
    ) -> str:
        """Generate human-readable potential impact description."""
        descriptions = {
            ("clinical_trial", "CRITICAL"): f"{'Positive' if sentiment_label == 'positive' else 'Negative'} clinical trial result may materially affect future product expectations and valuation.",
            ("clinical_trial", "HIGH"): f"Clinical trial {'success' if sentiment_label == 'positive' else 'concern'} may influence product pipeline outlook.",
            ("fda_approval", "CRITICAL"): "FDA approval enables commercial pathway and may significantly impact revenue expectations.",
            ("fda_rejection", "CRITICAL"): "FDA setback may significantly impair commercialization timeline and revenue expectations.",
            ("earnings_release", "HIGH"): f"{'Strong' if sentiment_label == 'positive' else 'Weak'} earnings may signal {'improving' if sentiment_label == 'positive' else 'challenging'} fundamental trajectory.",
            ("earnings_release", "CRITICAL"): f"{'Exceptional' if sentiment_label == 'positive' else 'Significant'} earnings {'beat' if sentiment_label == 'positive' else 'miss'} with potential for major price reaction.",
            ("guidance_change", "HIGH"): f"{'Raised' if sentiment_label == 'positive' else 'Lowered'} guidance {'improves' if sentiment_label == 'positive' else 'reduces'} forward expectations.",
            ("merger_acquisition", "CRITICAL"): "M&A event may result in significant price movement and potential arbitrage opportunity.",
            ("major_contract", "HIGH"): "Major contract may provide significant revenue visibility and growth catalyst.",
        }

        return descriptions.get(
            (catalyst_type, impact),
            f"{catalyst_type.replace('_', ' ').title()} event detected with {impact.lower()} impact potential."
        )

    def classify_article(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Classify a single news article into a catalyst event.
        Returns normalized catalyst dict or None if not a catalyst.
        """
        title = article.get("title", "")
        summary = article.get("summary", "")
        text = f"{title}. {summary}" if summary else title

        if not text.strip():
            return None

        # Match catalyst types
        matches = self._match_catalyst_type(text)

        if not matches:
            return None

        # Use best match
        cat_type, config, confidence = matches[0]

        # Skip very low confidence matches to reduce noise
        if confidence < 0.25:
            return None

        # Sentiment
        sentiment_score, sentiment_label = self._determine_sentiment(text, cat_type, config)

        # Impact
        impact = self._assess_impact(cat_type, config, sentiment_label, text, confidence)

        # Content hash for dedup
        content_hash = self._compute_content_hash(title, article.get("url", ""))

        # Parse published_at
        pub_at = article.get("published_at")
        if isinstance(pub_at, str):
            try:
                pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
            except Exception:
                pub_at = None

        return {
            "symbol": article.get("symbol"),
            "company": article.get("company", ""),
            "headline": title,
            "summary": summary[:500] if summary else "",
            "source": article.get("source", ""),
            "url": article.get("url", ""),
            "published_at": pub_at,
            "catalyst_type": cat_type,
            "category": config.get("category", ""),
            "impact_level": impact,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "relevance_score": confidence,
            "confidence": confidence,
            "potential_impact": self._generate_potential_impact(cat_type, impact, sentiment_label),
            "long_term_view": self._generate_long_term_view(cat_type, sentiment_label, title),
            "short_term_view": self._generate_short_term_view(cat_type, impact, sentiment_label, title),
            "content_hash": content_hash,
            "provider": article.get("source", ""),
            "raw_data": article,
        }

    def classify_articles(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Classify multiple articles and return catalyst events, sorted by impact."""
        catalysts = []

        for article in articles:
            result = self.classify_article(article)
            if result:
                catalysts.append(result)

        # Sort: CRITICAL first, then HIGH, MEDIUM, LOW
        impact_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        catalysts.sort(
            key=lambda x: (
                impact_order.get(x["impact_level"], 4),
                -(x.get("confidence") or 0),
            )
        )

        return catalysts

    def detect_early_signals(
        self,
        recent_catalysts: List[Dict[str, Any]],
        historical_catalyst_counts: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Detect early warning signals from recent catalyst patterns.
        Returns signal assessment for a given symbol.
        """
        if not recent_catalysts:
            return {
                "signal": "none",
                "description": "No recent catalyst activity detected.",
                "attention_trend": "stable",
            }

        now = datetime.utcnow()
        count_24h = 0
        count_7d = 0
        high_impact_count = 0
        sentiments = []

        for cat in recent_catalysts:
            pub = cat.get("published_at")
            if not pub:
                continue
            if isinstance(pub, str):
                try:
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00").replace("+00:00", ""))
                except Exception:
                    continue

            age = (now - pub).total_seconds()
            if age < 86400:  # 24h
                count_24h += 1
            if age < 604800:  # 7d
                count_7d += 1

            if cat.get("impact_level") in ("HIGH", "CRITICAL"):
                high_impact_count += 1

            if cat.get("sentiment_score") is not None:
                sentiments.append(cat["sentiment_score"])

        # Determine attention trend
        prev_7d = (historical_catalyst_counts or {}).get("7d", count_7d)
        if count_7d > prev_7d * 1.5:
            attention_trend = "increasing"
        elif count_7d < prev_7d * 0.5:
            attention_trend = "decreasing"
        else:
            attention_trend = "stable"

        # Generate signal description
        signal_parts = []
        signal_level = "none"

        if count_24h >= 3:
            signal_parts.append(f"High news frequency: {count_24h} articles in 24 hours")
            signal_level = "elevated"
        elif count_24h >= 2:
            signal_parts.append(f"Moderate news frequency: {count_24h} articles in 24 hours")
            signal_level = "mild"

        if high_impact_count >= 2:
            signal_parts.append(f"{high_impact_count} high-impact events this week")
            signal_level = "elevated" if signal_level != "elevated" else "high"
        elif high_impact_count >= 1:
            signal_parts.append(f"{high_impact_count} high-impact event this week")
            if signal_level == "none":
                signal_level = "mild"

        if attention_trend == "increasing":
            signal_parts.append("Attention increasing")
            if signal_level == "none":
                signal_level = "mild"

        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        if abs(avg_sentiment) > 0.3:
            direction = "positive" if avg_sentiment > 0 else "negative"
            signal_parts.append(f"Consistently {direction} sentiment")

        if not signal_parts:
            signal_parts.append("Normal activity levels")

        description = ". ".join(signal_parts)

        return {
            "signal": signal_level,
            "description": description,
            "attention_trend": attention_trend,
            "news_count_24h": count_24h,
            "news_count_7d": count_7d,
            "high_impact_count": high_impact_count,
            "avg_sentiment": round(avg_sentiment, 3),
        }

    def deduplicate_catalysts(
        self, catalysts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate catalyst events based on content hash and symbol."""
        seen = set()
        unique = []

        for cat in catalysts:
            key = f"{cat.get('symbol', '')}:{cat.get('content_hash', '')}"
            if key not in seen:
                seen.add(key)
                unique.append(cat)

        return unique

    def filter_actionable(
        self,
        catalysts: List[Dict[str, Any]],
        portfolio_symbols: Optional[set] = None,
        watchlist_symbols: Optional[set] = None,
        min_impact: str = "MEDIUM",
    ) -> List[Dict[str, Any]]:
        """
        Filter catalysts to only actionable, relevant events.
        Reduces noise and prevents alert fatigue.
        """
        impact_threshold = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        min_level = impact_threshold.get(min_impact, 1)

        filtered = []
        portfolio_symbols = portfolio_symbols or set()
        watchlist_symbols = watchlist_symbols or set()

        for cat in catalysts:
            cat_level = impact_threshold.get(cat.get("impact_level", "LOW"), 0)

            # Skip low-impact unless it affects portfolio/watchlist
            if cat_level < min_level:
                symbol = cat.get("symbol", "")
                if symbol not in portfolio_symbols and symbol not in watchlist_symbols:
                    continue

            # Mark portfolio/watchlist relevance
            symbol = cat.get("symbol", "")
            cat["affects_holding"] = 1 if symbol in portfolio_symbols else 0
            cat["affects_watchlist"] = 1 if symbol in watchlist_symbols else 0

            # Skip very low confidence
            if (cat.get("confidence") or 0) < 0.3:
                continue

            filtered.append(cat)

        return filtered

    # ── Legacy interface (backward compat with AnalysisService) ──

    def detect_from_news(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Legacy method for backward compatibility with AnalysisService."""
        catalysts = self.classify_articles(articles)
        # Convert to old format
        return [
            {
                "event_type": c["catalyst_type"],
                "title": c["headline"],
                "description": c["summary"],
                "date": c["published_at"].isoformat() if isinstance(c.get("published_at"), datetime) else str(c.get("published_at", "")),
                "impact": c["impact_level"].lower(),
                "sentiment": c["sentiment_label"],
                "source": c["source"],
                "url": c["url"],
                "symbol": c["symbol"],
            }
            for c in catalysts
        ]

    def detect_from_calendar(self, earnings_data: Dict[str, Any], info: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Legacy method for backward compatibility."""
        catalysts = []

        earnings_dates = earnings_data.get("earnings_dates", [])
        if earnings_dates:
            for ed in earnings_dates[:2]:
                date_str = None
                if isinstance(ed, dict):
                    date_str = ed.get("Earnings Date") or ed.get("date")
                catalysts.append({
                    "event_type": "earnings",
                    "title": "Upcoming Earnings Report",
                    "description": "Earnings report scheduled",
                    "date": date_str,
                    "impact": "high",
                    "sentiment": "neutral",
                })

        if info:
            ex_div = info.get("ex_dividend_date")
            if ex_div and ex_div != "None":
                catalysts.append({
                    "event_type": "dividend",
                    "title": "Ex-Dividend Date",
                    "description": f"Ex-dividend date: {ex_div}",
                    "date": ex_div,
                    "impact": "low",
                    "sentiment": "neutral",
                })

        return catalysts

    def get_all_catalysts(
        self,
        articles: List[Dict[str, Any]],
        earnings_data: Optional[Dict] = None,
        info: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Legacy method: Get all catalysts from all sources."""
        news_catalysts = self.detect_from_news(articles)
        calendar_catalysts = []
        if earnings_data:
            calendar_catalysts = self.detect_from_calendar(earnings_data, info)

        all_catalysts = news_catalysts + calendar_catalysts

        high_impact = [c for c in all_catalysts if c["impact"] == "high"]
        medium_impact = [c for c in all_catalysts if c["impact"] == "medium"]
        low_impact = [c for c in all_catalysts if c["impact"] == "low"]

        return {
            "catalysts": all_catalysts,
            "high_impact": high_impact,
            "medium_impact": medium_impact,
            "low_impact": low_impact,
            "total_count": len(all_catalysts),
            "has_upcoming_earnings": any(c["event_type"] == "earnings" for c in calendar_catalysts),
        }
