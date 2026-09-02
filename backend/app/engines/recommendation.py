"""
Recommendation engine — multi-factor, risk-profile-aware, anti-panic-sell.

Recommendation hierarchy:
  BUY        — strong multi-factor evidence across fundamentals, valuation, trend
  HOLD       — no urgent action; fundamentals intact
  WATCH      — monitor: some negative signals but not yet actionable
  TAKE PROFIT— strong fundamentals but position is extended / overweight
  REDUCE     — multiple deterioration factors; consider trimming
  SELL       — persistent fundamental + catalyst + risk deterioration

CRITICAL RULE: a single negative factor (price drop, one bad article,
RSI oversold, one earnings miss) MUST NOT trigger SELL.
Multi-factor confirmation is required before any negative recommendation.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Weights by risk profile ─────────────────────────────
WEIGHT_PROFILES = {
    "conservative": {
        "fundamental": 30, "valuation": 20, "trend": 10,
        "risk": 25, "sentiment": 5, "catalyst": 5, "portfolio_fit": 5,
    },
    "moderate": {
        "fundamental": 25, "valuation": 15, "trend": 15,
        "risk": 15, "sentiment": 10, "catalyst": 10, "portfolio_fit": 10,
    },
    "aggressive": {
        "fundamental": 15, "valuation": 10, "trend": 30,
        "risk": 10, "sentiment": 15, "catalyst": 15, "portfolio_fit": 5,
    },
}

# Thresholds for composite score → action mapping
ACTION_THRESHOLDS = {
    "BUY": 78,
    "HOLD": 55,
    "WATCH": 42,
    "REDUCE": 28,
    "SELL": 15,
}


class RecommendationEngine:
    """Generates explainable, risk-aware, anti-panic-sell recommendations."""

    def recommend(
        self,
        symbol: str,
        fundamental_score: float = 50,
        fundamental_data: Optional[Dict] = None,
        technical_data: Optional[Dict] = None,
        risk_data: Optional[Dict] = None,
        sentiment_data: Optional[Dict] = None,
        catalyst_data: Optional[Dict] = None,
        portfolio_allocation: float = 0,
        unrealized_gain_pct: Optional[float] = None,
        risk_profile: str = "moderate",
        investment_style: str = "balanced",
    ) -> Dict[str, Any]:
        """Generate a recommendation with full explanation."""

        weights = dict(WEIGHT_PROFILES.get(risk_profile, WEIGHT_PROFILES["moderate"]))

        # Investment style modifier
        if investment_style == "long_term":
            weights["fundamental"] = weights.get("fundamental", 25) + 10
            weights["trend"] = max(5, weights.get("trend", 15) - 5)
            weights["catalyst"] = max(5, weights.get("catalyst", 10) - 5)
        elif investment_style == "active":
            weights["trend"] = weights.get("trend", 15) + 10
            weights["catalyst"] = weights.get("catalyst", 10) + 5
            weights["fundamental"] = max(5, weights.get("fundamental", 25) - 10)

        # Normalize weights to sum to 100
        total_w = sum(weights.values())
        if total_w > 0:
            weights = {k: round(v * 100 / total_w, 1) for k, v in weights.items()}
        scores: Dict[str, float] = {}
        positive_factors: List[str] = []
        negative_factors: List[str] = []
        contradicting_factors: List[str] = []
        risks: List[str] = []
        what_would_change: List[str] = []
        data_available = 0

        # ── Classify each input into signal categories ──
        # negative_signal_categories tracks WHAT TYPE of negative signal we see
        negative_signal_categories = set()

        # ── Fundamental Score ────────────────────────────
        if fundamental_data and fundamental_data.get("score", 0) > 0:
            f_score = fundamental_data["score"]
            scores["fundamental"] = f_score
            data_available += 1
            if f_score >= 70:
                positive_factors.append(f"Strong fundamentals (score: {f_score:.0f}/100)")
            elif f_score >= 50:
                pass  # neutral — no positive or negative
            elif f_score >= 30:
                negative_factors.append(f"Weak fundamentals (score: {f_score:.0f}/100)")
                negative_signal_categories.add("fundamental")
                what_would_change.append("Improvement in revenue growth, margins, or profitability")
            else:
                negative_factors.append(f"Very weak fundamentals (score: {f_score:.0f}/100)")
                negative_signal_categories.add("fundamental")
                what_would_change.append("Significant fundamental improvement needed")
        else:
            scores["fundamental"] = 50

        # ── Valuation Score ──────────────────────────────
        val_score = 50
        if fundamental_data:
            metrics = fundamental_data.get("metrics", {})
            pe = metrics.get("pe_ratio")
            peg = metrics.get("peg_ratio")
            pb = metrics.get("price_to_book")

            val_factors = []
            if pe and pe > 0:
                if pe < 15:
                    val_factors.append(85)
                    positive_factors.append(f"Attractive valuation (P/E: {pe:.1f}x)")
                elif pe < 25:
                    val_factors.append(65)
                elif pe < 40:
                    val_factors.append(40)
                    negative_factors.append(f"Elevated valuation (P/E: {pe:.1f}x)")
                    negative_signal_categories.add("valuation")
                    what_would_change.append("Earnings growth accelerating to justify valuation")
                else:
                    val_factors.append(20)
                    negative_factors.append(f"Very high valuation (P/E: {pe:.1f}x)")
                    negative_signal_categories.add("valuation")

            if peg and peg > 0:
                if peg < 1:
                    val_factors.append(85)
                elif peg < 2:
                    val_factors.append(60)
                else:
                    val_factors.append(30)

            if val_factors:
                val_score = sum(val_factors) / len(val_factors)
                data_available += 1

        scores["valuation"] = val_score

        # ── Trend Score ──────────────────────────────────
        trend_score = 50
        if technical_data:
            trend = technical_data.get("trend", "Neutral")
            trend_strength = technical_data.get("trend_strength", 50)
            trend_score = trend_strength
            data_available += 1

            if trend in ("Strong Uptrend", "Uptrend"):
                positive_factors.append(f"Positive price trend ({trend})")
            elif trend in ("Strong Downtrend", "Downtrend"):
                negative_factors.append(f"Negative price trend ({trend})")
                negative_signal_categories.add("technical")
                risks.append("Downtrend may continue — watch for trend reversal signals")
                what_would_change.append("Price crossing above key moving averages")
            else:
                # Neutral trend is NOT a negative signal
                pass

            # Momentum
            momentum = technical_data.get("momentum", "Neutral")
            if "Bullish" in momentum:
                positive_factors.append(f"Bullish momentum ({momentum})")
            elif "Bearish" in momentum:
                # Bearish momentum alone is NOT a sell signal — it's a watch signal
                negative_factors.append(f"Bearish momentum ({momentum})")
                negative_signal_categories.add("technical")

        scores["trend"] = trend_score

        # ── Risk Score ───────────────────────────────────
        risk_score_val = 50
        if risk_data:
            stock_risk = risk_data.get("risk_score", 50)
            risk_score_val = 100 - stock_risk
            data_available += 1

            if stock_risk > 70:
                risks.append(f"High risk stock (risk score: {stock_risk:.0f}/100)")
                negative_signal_categories.add("risk")
            elif stock_risk < 30:
                positive_factors.append("Low risk profile")

            vol = risk_data.get("volatility")
            if vol and vol > 0.4:
                risks.append(f"High volatility ({vol*100:.0f}% annualized)")
                negative_signal_categories.add("risk")

            dd = risk_data.get("max_drawdown")
            if dd and abs(dd) > 0.3:
                risks.append(f"Historical max drawdown of {abs(dd)*100:.0f}%")

        scores["risk"] = risk_score_val

        # ── Sentiment Score ──────────────────────────────
        sent_score = 50
        if sentiment_data:
            overall = sentiment_data.get("overall_score", 0)
            sent_score = 50 + (overall * 50)
            data_available += 1

            sentiment_label = sentiment_data.get("overall_sentiment", "Neutral")
            if sentiment_label == "Positive":
                positive_factors.append("Positive news sentiment")
            elif sentiment_label == "Negative":
                # ONE negative news sentiment is NOT a sell signal
                negative_factors.append("Negative news sentiment")
                negative_signal_categories.add("sentiment")
                risks.append("Recent negative news may impact price short-term")
                what_would_change.append("Improvement in news sentiment")

        scores["sentiment"] = sent_score

        # ── Catalyst Score ───────────────────────────────
        cat_score = 50
        if catalyst_data and catalyst_data.get("catalysts"):
            catalysts = catalyst_data["catalysts"]
            positive_cats = [c for c in catalysts if c.get("sentiment") == "positive"]
            negative_cats = [c for c in catalysts if c.get("sentiment") == "negative"]

            if positive_cats:
                cat_score = 70
                positive_factors.append(f"Positive catalyst: {positive_cats[0].get('title', 'upcoming event')}")
            if negative_cats:
                cat_score = 30
                negative_factors.append(f"Negative catalyst: {negative_cats[0].get('title', 'recent event')}")
                negative_signal_categories.add("catalyst")
                what_would_change.append("Resolution or reversal of negative catalyst")
            data_available += 1

        scores["catalyst"] = cat_score

        # ── Portfolio Fit Score ──────────────────────────
        fit_score = 60
        if portfolio_allocation > 20:
            fit_score = 20
            negative_factors.append(f"Significantly overweight at {portfolio_allocation:.1f}% of portfolio")
            what_would_change.append("Reducing position size to lower concentration risk")
        elif portfolio_allocation > 15:
            fit_score = 30
            negative_factors.append(f"Overweight position at {portfolio_allocation:.1f}% of portfolio")
            negative_signal_categories.add("concentration")
        elif portfolio_allocation > 10:
            fit_score = 45
        elif portfolio_allocation > 0:
            fit_score = 65
            positive_factors.append(f"Reasonable portfolio weight ({portfolio_allocation:.1f}%)")

        scores["portfolio_fit"] = fit_score

        # ── Insufficient Data Check ──────────────────────
        if data_available < 2:
            return {
                "symbol": symbol,
                "recommendation": "WATCH",
                "confidence": 15,
                "confidence_label": "Very Low",
                "risk_level": "Unknown",
                "reasons": ["Not enough data to generate a reliable recommendation"],
                "positive_factors": positive_factors,
                "negative_factors": negative_factors,
                "contradicting_factors": [],
                "risks": ["Data unavailable — cannot assess risk"],
                "what_would_change": ["More data becoming available"],
                "explanation": f"Insufficient data to recommend {symbol}. Monitor until more information is available.",
                "data_freshness": "insufficient",
"last_analyzed": datetime.utcnow().isoformat(),
            }

        # ── Weighted Composite Score ─────────────────────
        total_weight = sum(weights.values())
        weighted_score = sum(
            scores.get(k, 50) * (w / total_weight)
            for k, w in weights.items()
        )

        # ── Anti-Panic-Sell: Multi-Factor Confirmation ───
        # Count how many DISTINCT categories have negative signals.
        # Single negative factor → WATCH (not REDUCE/SELL)
        # Two negative factors → WATCH or REDUCE depending on categories
        # Three+ negative factors including fundamental → REDUCE/SELL candidate
        num_negative_categories = len(negative_signal_categories)

        has_fundamental_deterioration = "fundamental" in negative_signal_categories
        has_valuation_deterioration = "valuation" in negative_signal_categories
        has_catalyst_deterioration = "catalyst" in negative_signal_categories
        has_risk_deterioration = "risk" in negative_signal_categories

        # ── Determine Recommendation ─────────────────────
        recommendation = self._determine_recommendation(
            weighted_score, unrealized_gain_pct, portfolio_allocation,
            risk_profile, num_negative_categories, has_fundamental_deterioration,
            has_valuation_deterioration, has_catalyst_deterioration,
            has_risk_deterioration,
        )

        # ── Confidence Score (0-100) ─────────────────────
        confidence = self._calculate_confidence(
            data_available, weighted_score, recommendation,
            num_negative_categories, negative_factors, positive_factors,
        )

        # ── Risk Level ───────────────────────────────────
        risk_level = self._assess_risk_level(risk_data, risks)

        # ── Build supporting/contradicting ────────────────
        contradicting_factors = self._build_contradicting(
            recommendation, positive_factors, negative_factors
        )

        # ── Reasons ──────────────────────────────────────
        reasons = self._generate_reasons(
            recommendation, positive_factors, negative_factors, risks,
            num_negative_categories, has_fundamental_deterioration,
        )

        # ── Explanation ──────────────────────────────────
        explanation = self._generate_explanation(
            symbol, recommendation, confidence, weighted_score,
            positive_factors, negative_factors, risks,
            num_negative_categories, has_fundamental_deterioration,
        )

        return {
            "symbol": symbol,
            "recommendation": recommendation,
            "confidence": round(confidence),
            "confidence_label": self._confidence_label(confidence),
            "risk_level": risk_level,
            "score": round(weighted_score, 1),
            "reasons": reasons[:5],
            "positive_factors": positive_factors[:5],
            "negative_factors": negative_factors[:5],
            "contradicting_factors": contradicting_factors[:3],
            "risks": risks[:5],
            "what_would_change": what_would_change[:4],
            "fundamental_input": round(scores.get("fundamental", 50), 1),
            "technical_input": round(scores.get("trend", 50), 1),
            "sentiment_input": round(scores.get("sentiment", 50), 1),
            "risk_input": round(scores.get("risk", 50), 1),
            "valuation_input": round(scores.get("valuation", 50), 1),
            "explanation": explanation,
            "data_freshness": "calculated",
            "last_analyzed": datetime.utcnow().isoformat(),
            "anti_panic_note": self._anti_panic_note(
                recommendation, num_negative_categories,
                has_fundamental_deterioration, negative_factors,
            ),
        }

    def _determine_recommendation(
        self, score: float, gain_pct: Optional[float],
        allocation: float, profile: str,
        num_negative: int, has_fundamental: bool,
        has_valuation: bool, has_catalyst: bool, has_risk: bool,
    ) -> str:
        """Determine recommendation with multi-factor confirmation.

        CRITICAL: single negative factors do NOT trigger SELL/REDUCE.
        """
        # ── TAKE PROFIT: high score + very high unrealized gain ──
        if gain_pct and gain_pct > 100 and allocation > 10:
            if profile == "conservative":
                return "TAKE PROFIT"
            elif profile == "moderate" and gain_pct > 150:
                return "TAKE PROFIT"

        # ── SELL: requires persistent fundamental deterioration + catalyst or risk ──
        # Must have BOTH fundamental deterioration AND at least one of: catalyst, risk, valuation
        if has_fundamental and (has_catalyst or has_risk or has_valuation) and num_negative >= 3:
            if score < 25:
                return "SELL"
            elif score < 35:
                return "REDUCE"

        # ── REDUCE: overweight or multiple deterioration factors ──
        if allocation > 20 and profile in ("conservative", "moderate"):
            return "REDUCE"
        if num_negative >= 3 and has_fundamental:
            return "REDUCE"
        if num_negative >= 2 and has_fundamental and has_valuation:
            return "REDUCE"

        # ── Standard score-based mapping ──
        if score >= ACTION_THRESHOLDS["BUY"]:
            return "BUY"
        elif score >= ACTION_THRESHOLDS["HOLD"]:
            return "HOLD"
        elif score >= ACTION_THRESHOLDS["WATCH"]:
            return "WATCH"
        elif score >= ACTION_THRESHOLDS["REDUCE"]:
            # Only REDUCE if multiple factors confirm
            if num_negative >= 2:
                return "REDUCE"
            return "WATCH"  # Single negative → stay at WATCH
        elif score >= ACTION_THRESHOLDS["SELL"]:
            # Only SELL if fundamental deterioration is present
            if has_fundamental and num_negative >= 2:
                return "REDUCE"
            return "WATCH"  # Don't panic sell on technical/sentiment alone
        else:
            if has_fundamental and num_negative >= 2:
                return "SELL"
            return "REDUCE"

    def _calculate_confidence(
        self, data_available: int, score: float, recommendation: str,
        num_negative: int, negatives: List[str], positives: List[str],
    ) -> float:
        """Calculate confidence 0-100 based on data quality and signal clarity."""
        # Base from data availability
        if data_available >= 5:
            base = 70
        elif data_available >= 3:
            base = 55
        else:
            base = 35

        # Score extremity adds confidence
        extremity = abs(score - 50) / 50  # 0..1
        base += extremity * 20

        # Contradictory signals reduce confidence
        if len(negatives) > 0 and len(positives) > 0:
            ratio = min(len(negatives), len(positives)) / max(len(negatives), len(positives), 1)
            base -= ratio * 15

        # Fewer negative categories = more confident in HOLD/BUY
        if recommendation in ("HOLD", "BUY") and num_negative <= 1:
            base += 5

        return max(15, min(95, base))

    def _confidence_label(self, confidence: float) -> str:
        if confidence >= 80:
            return "Strong"
        elif confidence >= 65:
            return "High"
        elif confidence >= 45:
            return "Medium"
        else:
            return "Low"

    def _assess_risk_level(self, risk_data: Optional[Dict], risks: List[str]) -> str:
        if not risk_data:
            return "Unknown"
        score = risk_data.get("risk_score", 50)
        if score <= 25:
            return "Low"
        elif score <= 50:
            return "Moderate"
        elif score <= 75:
            return "Elevated"
        else:
            return "High"

    def _build_contradicting(
        self, recommendation: str,
        positives: List[str], negatives: List[str],
    ) -> List[str]:
        """Factors that argue AGAINST the current recommendation."""
        if recommendation in ("BUY", "HOLD"):
            return negatives[:3]
        elif recommendation in ("REDUCE", "SELL"):
            return positives[:3]
        return []

    def _generate_reasons(
        self, action: str,
        positives: List[str], negatives: List[str],
        risks: List[str], num_negative: int,
        has_fundamental: bool,
    ) -> List[str]:
        """Generate top reasons — always include both sides."""
        reasons = []

        if action in ("BUY",):
            reasons.extend(positives[:3])
            if negatives:
                reasons.append(f"Note: {negatives[0]}")
        elif action == "HOLD":
            if positives:
                reasons.extend(positives[:2])
            reasons.append("No urgent action required — continue monitoring")
            if negatives:
                reasons.append(f"Watch: {negatives[0]}")
        elif action == "WATCH":
            reasons.extend(negatives[:2])
            if positives:
                reasons.append(f"However: {positives[0]}")
        elif action == "TAKE PROFIT":
            reasons.append("Significant unrealized gains — consider trimming position")
            reasons.extend(positives[:2])
        elif action == "REDUCE":
            reasons.extend(negatives[:2])
            if has_fundamental:
                reasons.append("Multiple deterioration factors confirmed")
            if positives:
                reasons.append(f"Note: {positives[0]}")
        elif action == "SELL":
            reasons.extend(negatives[:3])
            if risks:
                reasons.append(risks[0])
            reasons.append("Multi-factor deterioration confirmed — review position")
        else:
            reasons.extend(positives[:2] + negatives[:2])

        return reasons if reasons else ["Based on overall multi-factor analysis"]

    def _generate_explanation(
        self, symbol: str, action: str, confidence: float,
        score: float, positives: List, negatives: List, risks: List,
        num_negative: int, has_fundamental: bool,
    ) -> str:
        """Generate human-readable explanation."""
        conf_label = self._confidence_label(confidence)
        parts = [
            f"{symbol} receives a {action} recommendation "
            f"with {conf_label} confidence (model confidence: {confidence:.0f}/100)."
        ]

        if positives:
            parts.append(f"Supporting factors: {'; '.join(positives[:3])}.")

        if negatives:
            parts.append(f"Concerns: {'; '.join(negatives[:3])}.")

        if risks:
            parts.append(f"Key risks: {'; '.join(risks[:2])}.")

        if num_negative <= 1 and action in ("HOLD", "WATCH"):
            parts.append(
                "Note: the negative signals detected appear to be short-term or "
                "technical in nature. Multi-factor confirmation for a SELL or REDUCE "
                "recommendation has NOT been met."
            )

        return " ".join(parts)

    def _anti_panic_note(
        self, recommendation: str, num_negative: int,
        has_fundamental: bool, negatives: List[str],
    ) -> Optional[str]:
        """Generate anti-panic-sell context note."""
        if recommendation in ("SELL", "REDUCE"):
            return None  # No anti-panic note if we ARE recommending reduction

        if num_negative == 0:
            return None

        if num_negative == 1:
            return (
                "Only one negative factor detected. The recommendation engine requires "
                "multi-factor confirmation before recommending SELL or REDUCE. "
                "This appears to be normal volatility or a temporary pullback."
            )

        if num_negative == 2 and not has_fundamental:
            return (
                "Two negative factors detected but fundamental analysis remains intact. "
                "This does not meet the threshold for a REDUCE recommendation. "
                "Monitor for any fundamental deterioration."
            )

        return None
