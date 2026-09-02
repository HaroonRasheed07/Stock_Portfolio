"""
Rule-based explanation engine.
Generates structured, actionable portfolio health reports with strengths, risks,
and prioritised actions — not just a narrative blob.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class RuleBasedAI:
    """Generates structured portfolio health reports with actionable insights."""

    def generate_portfolio_health_report(
        self,
        summary: Dict[str, Any],
        risk: Dict[str, Any],
        diversification: Dict[str, Any],
        holdings: List[Dict[str, Any]],
        news: List[Dict[str, Any]] = None,
        per_holding_analysis: Dict[str, Dict] = None,
    ) -> Dict[str, Any]:
        """Generate a complete structured portfolio health report."""
        val = summary.get("total_value", 0)
        cost = summary.get("total_cost_basis", 0)
        gain = summary.get("total_gain_loss", 0)
        gain_pct = summary.get("total_gain_loss_pct", 0)

        risk_score = risk.get("risk_score", 50)
        risk_level = risk.get("risk_level", "Moderate")
        div_score = diversification.get("score", 50)
        div_level = diversification.get("level", "Moderate")

        # ── Composite health score ─────────────────────────
        perf_score = min(100, max(0, 50 + gain_pct * 0.5))
        risk_health = 100 - risk_score
        health_score = round(perf_score * 0.3 + risk_health * 0.35 + div_score * 0.35, 1)

        # Grade from score
        if health_score >= 80:
            grade = "A"
        elif health_score >= 65:
            grade = "B"
        elif health_score >= 50:
            grade = "C"
        elif health_score >= 35:
            grade = "D"
        else:
            grade = "F"

        # ── Holdings analysis ──────────────────────────────
        sorted_by_gain = sorted(
            holdings,
            key=lambda x: x.get("unrealized_gain_pct") or 0,
            reverse=True,
        )
        strong_holdings = self._format_holdings(sorted_by_gain[:3], "strong")
        weak_holdings = self._format_holdings(sorted_by_gain[-3:][::-1], "weak")

        # ── Strengths ──────────────────────────────────────
        strengths = self._identify_strengths(
            health_score, perf_score, risk_health, div_score,
            holdings, sorted_by_gain, risk, diversification,
        )

        # ── Risks ──────────────────────────────────────────
        risks = self._identify_risks(
            risk_score, risk_level, div_score, div_level,
            holdings, risk, diversification, news,
        )

        # ── Actions ────────────────────────────────────────
        actions = self._generate_actions(
            risks, holdings, sorted_by_gain, div_level,
            risk_score, div_score,
        )

        # ── What Should I Do? section ──────────────────────
        what_should_i_do = self._generate_what_should_i_do(
            risks, actions, holdings, health_score, grade,
        )

        # ── Concerns (backward-compatible) ─────────────────
        concerns = []
        if risk_score > 60:
            concerns.append("Portfolio risk score is elevated due to concentration or high volatility holdings.")
        if div_score < 50:
            concerns.append("Diversification is below optimal levels. Portfolio has sector or position concentration.")
        for h in holdings:
            if (h.get("allocation_pct") or 0) > 15:
                concerns.append(
                    f"Position concentration: {h['symbol']} makes up "
                    f"{h['allocation_pct']:.1f}% of the portfolio."
                )

        # ── Opportunities ──────────────────────────────────
        opportunities = []
        if div_level in ("Moderate", "Poor", "Critical"):
            opportunities.append("Rebalance funds into underrepresented sectors to lower portfolio volatility.")
        if any((h.get("unrealized_gain_pct") or 0) > 100 for h in holdings):
            opportunities.append("Consider taking partial profits on positions with >100% gains.")

        # ── Executive summary (compact) ────────────────────
        executive_summary = (
            f"Portfolio valued at ${val:,.2f} with {gain_pct:+.2f}% unrealized return "
            f"(${gain:+,.2f}). Health score: {health_score}/100 (grade {grade}). "
            f"Risk: {risk_level.lower()} ({risk_score}/100). "
            f"Diversification: {div_level.lower()} ({div_score}/100)."
        )

        # ── Full narrative (backward-compatible) ───────────
        narrative = (
            f"Portfolio Health Report (Overall Score: {health_score}/100)\n\n"
            f"1. Executive Summary:\n{executive_summary}\n\n"
            f"2. Performance & Holdings:\n"
            f"Top performer: {strong_holdings[0]['symbol'] if strong_holdings else 'N/A'} "
            f"({strong_holdings[0].get('unrealized_gain_pct', 0):+.1f}%). "
            f"Lagging position: {weak_holdings[0]['symbol'] if weak_holdings else 'N/A'} "
            f"({weak_holdings[0].get('unrealized_gain_pct', 0):+.1f}%).\n\n"
            f"3. Risk & Diversification Assessment:\n"
            f"{risk.get('explanation', '')} {diversification.get('explanation', '')}\n\n"
            f"4. Actionable Insights:\n"
            f"- Concerns: {'; '.join(concerns[:3]) if concerns else 'No major concerns detected.'}\n"
            f"- Opportunities: {'; '.join(opportunities[:3]) if opportunities else 'Maintain current allocation.'}"
        )

        return {
            # Structured sections
            "overall_score": health_score,
            "grade": grade,
            "executive_summary": executive_summary,
            "strengths": strengths,
            "risks": risks,
            "actions": actions,
            "what_should_i_do": what_should_i_do,

            # Detailed breakdown
            "strong_holdings": strong_holdings,
            "weak_holdings": weak_holdings,
            "important_news": news[:5] if news else [],
            "fundamental_concerns": concerns,
            "concentration_risks": diversification.get("warnings", []),
            "opportunities": opportunities,
            "items_to_monitor": [
                f"Monitor {w['symbol']} performance" for w in weak_holdings
            ] if weak_holdings else [],

            # Per-holding recommendations (from technical + fundamental data)
            "per_holding_recommendations": self._generate_per_holding_recommendations(
                holdings, per_holding_analysis or {}
            ),

            # Score breakdown
            "score_breakdown": {
                "performance": round(perf_score, 1),
                "risk_health": round(risk_health, 1),
                "diversification": round(div_score, 1),
            },

            # Sub-scores for UI charts
            "risk_assessment": risk.get("explanation", ""),
            "diversification_assessment": diversification.get("explanation", ""),
            "performance_assessment": f"Total return: {gain_pct:+.2f}%",

            # Backward-compat narrative
            "full_report": narrative,
            "last_analyzed": datetime.utcnow().isoformat(),
        }

    # ── Private helpers ────────────────────────────────────

    def _format_holdings(self, holdings: List[Dict], label: str) -> List[Dict]:
        """Format holdings for display."""
        result = []
        for h in holdings:
            result.append({
                "symbol": h.get("symbol", ""),
                "name": h.get("name", ""),
                "unrealized_gain_pct": round(h.get("unrealized_gain_pct") or 0, 2),
                "allocation_pct": round(h.get("allocation_pct") or 0, 2),
                "current_price": h.get("current_price"),
                "current_value": h.get("current_value"),
                "cost_basis": h.get("cost_basis"),
            })
        return result

    def _identify_strengths(
        self, health_score, perf_score, risk_health, div_score,
        holdings, sorted_by_gain, risk, diversification,
    ) -> List[Dict[str, str]]:
        strengths = []

        if health_score >= 70:
            strengths.append({
                "type": "overall",
                "label": "Strong Portfolio Health",
                "detail": f"Overall health score of {health_score}/100 indicates a well-managed portfolio.",
            })
        if perf_score >= 65:
            strengths.append({
                "type": "performance",
                "label": "Strong Performance",
                "detail": f"Unrealized gains are above average. Performance score: {perf_score:.0f}/100.",
            })
        if risk_health >= 60:
            strengths.append({
                "type": "risk",
                "label": "Well-Managed Risk",
                "detail": f"Portfolio risk is below the market average. Risk health: {risk_health:.0f}/100.",
            })
        if div_score >= 70:
            strengths.append({
                "type": "diversification",
                "label": "Good Diversification",
                "detail": f"Portfolio is well-diversified across sectors and positions. Score: {div_score:.0f}/100.",
            })

        # Top performers
        if sorted_by_gain and (sorted_by_gain[0].get("unrealized_gain_pct") or 0) > 50:
            h = sorted_by_gain[0]
            strengths.append({
                "type": "holding",
                "label": f"Top Performer: {h['symbol']}",
                "detail": f"{h['symbol']} is up {h.get('unrealized_gain_pct', 0):+.1f}%, "
                          f"contributing significantly to portfolio gains.",
            })

        # Low concentration
        over_15 = [h for h in holdings if (h.get("allocation_pct") or 0) > 15]
        if not over_15:
            strengths.append({
                "type": "concentration",
                "label": "No Single-Position Overweight",
                "detail": "No position exceeds 15% of portfolio, reducing concentration risk.",
            })

        return strengths if strengths else [{
            "type": "overall",
            "label": "Portfolio Exists",
            "detail": "Portfolio is active but may need attention in several areas.",
        }]

    def _identify_risks(
        self, risk_score, risk_level, div_score, div_level,
        holdings, risk, diversification, news,
    ) -> List[Dict[str, str]]:
        risks = []

        if risk_score > 70:
            risks.append({
                "type": "risk_score",
                "severity": "high",
                "label": "Elevated Portfolio Risk",
                "detail": f"Risk score is {risk_score}/100 ({risk_level}). "
                          f"This may result in larger-than-expected drawdowns during market stress.",
            })
        elif risk_score > 50:
            risks.append({
                "type": "risk_score",
                "severity": "medium",
                "label": "Moderate Portfolio Risk",
                "detail": f"Risk score is {risk_score}/100 ({risk_level}). "
                          f"Monitor volatility and correlation between holdings.",
            })

        # Diversification
        if div_score < 40:
            risks.append({
                "type": "diversification",
                "severity": "high",
                "label": "Poor Diversification",
                "detail": f"Diversification score is {div_score}/100 ({div_level}). "
                          f"Portfolio is heavily concentrated in a few sectors or positions.",
            })
        elif div_score < 55:
            risks.append({
                "type": "diversification",
                "severity": "medium",
                "label": "Diversification Could Improve",
                "detail": f"Diversification score is {div_score}/100 ({div_level}). "
                          f"Consider adding holdings in underrepresented sectors.",
            })

        # Position concentration
        for h in holdings:
            alloc = h.get("allocation_pct") or 0
            if alloc > 20:
                risks.append({
                    "type": "concentration",
                    "severity": "high",
                    "label": f"{h['symbol']} Overweight ({alloc:.1f}%)",
                    "detail": f"{h['symbol']} represents {alloc:.1f}% of portfolio. "
                              f"A decline in this single position will disproportionately impact returns.",
                })
            elif alloc > 15:
                risks.append({
                    "type": "concentration",
                    "severity": "medium",
                    "label": f"{h['symbol']} Large Position ({alloc:.1f}%)",
                    "detail": f"{h['symbol']} is {alloc:.1f}% of portfolio, "
                              f"exceeding the recommended 15% single-position limit.",
                })

        # Concentration warnings from diversification engine
        for w in (diversification.get("warnings") or [])[:2]:
            if isinstance(w, str) and w not in [r.get("detail") for r in risks]:
                risks.append({
                    "type": "diversification_warning",
                    "severity": "medium",
                    "label": "Concentration Warning",
                    "detail": w,
                })

        # Volatility from risk engine
        vol = risk.get("portfolio_volatility")
        if vol and vol > 0.30:
            risks.append({
                "type": "volatility",
                "severity": "high" if vol > 0.40 else "medium",
                "label": f"High Volatility ({vol*100:.1f}%)",
                "detail": f"Annualized portfolio volatility is {vol*100:.1f}%, "
                          f"above the typical 15-25% range.",
            })

        # Beta
        beta = risk.get("portfolio_beta")
        if beta and beta > 1.3:
            risks.append({
                "type": "beta",
                "severity": "medium",
                "label": f"Above-Market Beta ({beta:.2f})",
                "detail": f"Portfolio beta of {beta:.2f} means amplified moves relative to S&P 500.",
            })

        return risks

    def _generate_actions(
        self, risks, holdings, sorted_by_gain, div_level,
        risk_score, div_score,
    ) -> List[Dict[str, str]]:
        """Generate prioritised action items based on identified risks."""
        actions = []

        # HIGH concentration positions
        for h in holdings:
            alloc = h.get("allocation_pct") or 0
            if alloc > 20:
                actions.append({
                    "priority": "high",
                    "action": f"Reduce {h['symbol']} position from {alloc:.1f}%",
                    "reason": f"{h['symbol']} is overweight at {alloc:.1f}% "
                              f"of portfolio. Target <15% to reduce concentration risk.",
                    "estimated_impact": "Reduces single-position risk by "
                                        f"{alloc - 12:.1f} percentage points.",
                })
            elif alloc > 15:
                actions.append({
                    "priority": "medium",
                    "action": f"Trim {h['symbol']} position ({alloc:.1f}%)",
                    "reason": f"{h['symbol']} slightly exceeds the 15% threshold.",
                    "estimated_impact": "Moderate improvement in diversification score.",
                })

        # Diversification
        if div_score < 40:
            actions.append({
                "priority": "high",
                "action": "Rebalance into underrepresented sectors",
                "reason": f"Diversification is {div_level} ({div_score}/100). "
                          f"Portfolio lacks exposure to key market sectors.",
                "estimated_impact": "Could improve diversification score by 15-30 points.",
            })
        elif div_score < 55:
            actions.append({
                "priority": "medium",
                "action": "Add holdings in 2-3 underrepresented sectors",
                "reason": f"Diversification is {div_level} ({div_score}/100).",
                "estimated_impact": "Improved risk-adjusted returns.",
            })

        # Profit taking
        for h in sorted_by_gain[:2]:
            gain = h.get("unrealized_gain_pct") or 0
            alloc = h.get("allocation_pct") or 0
            if gain > 100 and alloc > 10:
                actions.append({
                    "priority": "medium",
                    "action": f"Consider taking partial profit on {h['symbol']} ({gain:+.1f}%)",
                    "reason": f"{h['symbol']} has more than doubled. "
                              f"Taking 10-20% of position locks in gains.",
                    "estimated_impact": "Reduces concentration while booking gains.",
                })

        # Risk management
        if risk_score > 70:
            actions.append({
                "priority": "high",
                "action": "Hedge or reduce exposure to high-volatility holdings",
                "reason": f"Portfolio risk score is {risk_score}/100. "
                          f"Consider protective puts or reducing volatile positions.",
                "estimated_impact": "Reduces potential drawdown in market correction.",
            })

        return actions if actions else [{
            "priority": "low",
            "action": "Continue monitoring portfolio",
            "reason": "No critical actions required at this time.",
            "estimated_impact": "Maintains current risk-return profile.",
        }]

    def _generate_what_should_i_do(
        self, risks, actions, holdings, health_score, grade,
    ) -> Dict[str, Any]:
        """Generate the 'What Should I Do?' summary section."""
        high_priority = [a for a in actions if a.get("priority") == "high"]
        medium_priority = [a for a in actions if a.get("priority") == "medium"]

        if high_priority:
            summary = (
                f"Your portfolio grade is {grade} ({health_score}/100). "
                f"There are {len(high_priority)} high-priority action(s) to address. "
                f"Focus on reducing concentration risk and improving diversification."
            )
        elif medium_priority:
            summary = (
                f"Your portfolio grade is {grade} ({health_score}/100). "
                f"There are {len(medium_priority)} medium-priority items to consider. "
                f"No urgent action required, but优化 the portfolio over time."
            )
        else:
            summary = (
                f"Your portfolio grade is {grade} ({health_score}/100). "
                f"No immediate action required. Continue monitoring and maintaining "
                f"your current allocation strategy."
            )

        return {
            "grade": grade,
            "health_score": health_score,
            "summary": summary,
            "high_priority_actions": high_priority,
            "medium_priority_actions": medium_priority,
            "next_review": "Review in 1-2 weeks or after significant market moves.",
        }

    def _generate_per_holding_recommendations(
        self,
        holdings: List[Dict[str, Any]],
        per_holding_analysis: Dict[str, Dict],
    ) -> List[Dict[str, Any]]:
        """Generate per-holding recommendations based on technical + fundamental data."""
        recommendations = []
        for h in holdings:
            sym = h["symbol"]
            analysis = per_holding_analysis.get(sym)
            if not analysis:
                recommendations.append({
                    "symbol": sym,
                    "name": h.get("name", sym),
                    "recommendation": "HOLD",
                    "reasoning": "Insufficient data for detailed analysis.",
                    "technical_summary": None,
                    "fundamental_summary": None,
                })
                continue

            technical = analysis.get("technical", {})
            fundamental = analysis.get("fundamental", {})
            tech_score = technical.get("trend_strength") or 50
            fund_score = fundamental.get("score") or 50
            trend = technical.get("trend", "Neutral")
            momentum = technical.get("momentum", "Neutral")
            gain_pct = h.get("unrealized_gain_pct") or 0

            # Determine recommendation based on multi-factor analysis
            reasons = []
            negative_factors = 0
            positive_factors = 0

            # Technical assessment
            if tech_score >= 70:
                positive_factors += 1
                reasons.append(f"Technical trend is strong ({trend}, strength {tech_score:.0f}/100)")
            elif tech_score < 40:
                negative_factors += 1
                reasons.append(f"Technical trend is weak ({trend}, strength {tech_score:.0f}/100)")

            # Fundamental assessment
            if fund_score >= 70:
                positive_factors += 1
                reasons.append(f"Fundamentals are solid (score {fund_score:.0f}/100)")
            elif fund_score < 40:
                negative_factors += 1
                reasons.append(f"Fundamentals are concerning (score {fund_score:.0f}/100)")

            # Valuation concerns
            weaknesses = fundamental.get("weaknesses", [])
            if weaknesses:
                negative_factors += 1
                reasons.append(f"Valuation concerns: {'; '.join(weaknesses[:2])}")

            strengths = fundamental.get("strengths", [])
            if strengths:
                positive_factors += 1
                reasons.append(f"Strengths: {'; '.join(strengths[:2])}")

            # Determine action
            if negative_factors >= 3 and positive_factors <= 1:
                recommendation = "REDUCE"
                reasoning = f"Multiple negative factors detected ({'; '.join(reasons[:3])}). Consider reducing position."
            elif negative_factors >= 2 and fund_score < 40:
                recommendation = "WATCH"
                reasoning = f"Moderate concerns ({'; '.join(reasons[:3])}). Monitor for further deterioration."
            elif positive_factors >= 3:
                recommendation = "INCREASE"
                reasoning = f"Strong signals ({'; '.join(reasons[:3])}). Consider increasing allocation."
            elif positive_factors >= 2:
                recommendation = "HOLD"
                reasoning = f"Solid fundamentals and technicals ({'; '.join(reasons[:3])}). Maintain position."
            else:
                recommendation = "HOLD"
                reasoning = "Mixed signals. Maintain current position and monitor."

            # Override for large losses with weak fundamentals
            if gain_pct < -20 and fund_score < 40 and tech_score < 40:
                recommendation = "REDUCE"
                reasoning = (
                    f"Significant unrealized loss ({gain_pct:+.1f}%) combined with weak "
                    f"fundamentals (score {fund_score:.0f}) and weak technicals (score {tech_score:.0f}). "
                    f"Consider reducing position. {'; '.join(reasons[:2])}"
                )

            technical_summary = (
                f"Trend: {trend} (strength {tech_score:.0f}/100), Momentum: {momentum}"
            )
            fundamental_summary = (
                f"Score: {fund_score:.0f}/100. "
                f"Strengths: {', '.join(strengths[:2]) if strengths else 'None identified'}. "
                f"Weaknesses: {', '.join(weaknesses[:2]) if weaknesses else 'None identified'}."
            )

            recommendations.append({
                "symbol": sym,
                "name": h.get("name", sym),
                "recommendation": recommendation,
                "reasoning": reasoning,
                "technical_summary": technical_summary,
                "fundamental_summary": fundamental_summary,
                "technical_score": round(tech_score, 1),
                "fundamental_score": round(fund_score, 1),
                "unrealized_gain_pct": round(gain_pct, 1) if gain_pct else 0,
            })

        # Sort: REDUCE first (most concerning), then WATCH, HOLD, INCREASE
        order = {"REDUCE": 0, "WATCH": 1, "HOLD": 2, "INCREASE": 3}
        recommendations.sort(key=lambda r: order.get(r["recommendation"], 99))
        return recommendations
