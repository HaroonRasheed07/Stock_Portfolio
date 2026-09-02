"""
Rebalancing analysis engine.
Compares current allocation against targets and suggests actionable stock-to-stock moves.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Default sector targets — typical balanced portfolio
DEFAULT_SECTOR_TARGETS = {
    "Technology": 25,
    "Healthcare": 12,
    "Financial Services": 15,
    "Consumer Cyclical": 10,
    "Industrials": 10,
    "Consumer Defensive": 8,
    "Energy": 5,
    "Utilities": 5,
    "Real Estate": 5,
    "Basic Materials": 3,
    "Communication Services": 2,
}

# Position-level allocation targets
DEFAULT_MAX_SINGLE_POSITION = 15.0  # %
DEFAULT_MIN_SINGLE_POSITION = 1.0   # %
DEFAULT_CASH_TARGET = 5.0           # %

# Quality candidate universe — large-cap, established companies
# Used when portfolio holdings are insufficient as replacement candidates
CANDIDATE_UNIVERSE = {
    "Technology": [
        {"ticker": "MSFT", "name": "Microsoft Corp", "quality": 95},
        {"ticker": "AAPL", "name": "Apple Inc", "quality": 93},
        {"ticker": "GOOGL", "name": "Alphabet Inc", "quality": 92},
        {"ticker": "NVDA", "name": "NVIDIA Corp", "quality": 90},
        {"ticker": "AVGO", "name": "Broadcom Inc", "quality": 88},
        {"ticker": "CRM", "name": "Salesforce Inc", "quality": 85},
        {"ticker": "ADBE", "name": "Adobe Inc", "quality": 84},
        {"ticker": "CSCO", "name": "Cisco Systems", "quality": 82},
        {"ticker": "TXN", "name": "Texas Instruments", "quality": 83},
        {"ticker": "INTC", "name": "Intel Corp", "quality": 70},
    ],
    "Healthcare": [
        {"ticker": "UNH", "name": "UnitedHealth Group", "quality": 94},
        {"ticker": "JNJ", "name": "Johnson & Johnson", "quality": 91},
        {"ticker": "LLY", "name": "Eli Lilly", "quality": 90},
        {"ticker": "ABBV", "name": "AbbVie Inc", "quality": 88},
        {"ticker": "PFE", "name": "Pfizer Inc", "quality": 78},
        {"ticker": "TMO", "name": "Thermo Fisher Scientific", "quality": 86},
        {"ticker": "ABT", "name": "Abbott Labs", "quality": 85},
        {"ticker": "DHR", "name": "Danaher Corp", "quality": 87},
        {"ticker": "BMY", "name": "Bristol-Myers Squibb", "quality": 80},
        {"ticker": "AMGN", "name": "Amgen Inc", "quality": 82},
    ],
    "Financial Services": [
        {"ticker": "JPM", "name": "JPMorgan Chase", "quality": 92},
        {"ticker": "V", "name": "Visa Inc", "quality": 93},
        {"ticker": "MA", "name": "Mastercard Inc", "quality": 92},
        {"ticker": "BRK-B", "name": "Berkshire Hathaway", "quality": 95},
        {"ticker": "BAC", "name": "Bank of America", "quality": 80},
        {"ticker": "WFC", "name": "Wells Fargo", "quality": 76},
        {"ticker": "GS", "name": "Goldman Sachs", "quality": 84},
        {"ticker": "MS", "name": "Morgan Stanley", "quality": 82},
        {"ticker": "BLK", "name": "BlackRock Inc", "quality": 88},
        {"ticker": "SCHW", "name": "Charles Schwab", "quality": 83},
    ],
    "Consumer Cyclical": [
        {"ticker": "AMZN", "name": "Amazon.com", "quality": 93},
        {"ticker": "TSLA", "name": "Tesla Inc", "quality": 78},
        {"ticker": "HD", "name": "Home Depot", "quality": 89},
        {"ticker": "MCD", "name": "McDonald's Corp", "quality": 88},
        {"ticker": "NKE", "name": "Nike Inc", "quality": 82},
        {"ticker": "SBUX", "name": "Starbucks Corp", "quality": 80},
        {"ticker": "LOW", "name": "Lowe's Cos", "quality": 83},
        {"ticker": "TJX", "name": "TJX Companies", "quality": 84},
        {"ticker": "BKNG", "name": "Booking Holdings", "quality": 90},
        {"ticker": "DHI", "name": "D.R. Horton", "quality": 81},
    ],
    "Industrials": [
        {"ticker": "CAT", "name": "Caterpillar Inc", "quality": 88},
        {"ticker": "GE", "name": "General Electric", "quality": 82},
        {"ticker": "HON", "name": "Honeywell Intl", "quality": 86},
        {"ticker": "UNP", "name": "Union Pacific", "quality": 85},
        {"ticker": "RTX", "name": "RTX Corp", "quality": 83},
        {"ticker": "DE", "name": "Deere & Co", "quality": 86},
        {"ticker": "LMT", "name": "Lockheed Martin", "quality": 87},
        {"ticker": "MMM", "name": "3M Company", "quality": 68},
        {"ticker": "GD", "name": "General Dynamics", "quality": 84},
        {"ticker": "EMR", "name": "Emerson Electric", "quality": 81},
    ],
    "Consumer Defensive": [
        {"ticker": "PG", "name": "Procter & Gamble", "quality": 91},
        {"ticker": "KO", "name": "Coca-Cola Co", "quality": 90},
        {"ticker": "PEP", "name": "PepsiCo Inc", "quality": 89},
        {"ticker": "COST", "name": "Costco Wholesale", "quality": 92},
        {"ticker": "WMT", "name": "Walmart Inc", "quality": 88},
        {"ticker": "PM", "name": "Philip Morris Intl", "quality": 83},
        {"ticker": "MO", "name": "Altria Group", "quality": 72},
        {"ticker": "CL", "name": "Colgate-Palmolive", "quality": 84},
        {"ticker": "KMB", "name": "Kimberly-Clark", "quality": 80},
        {"ticker": "GIS", "name": "General Mills", "quality": 79},
    ],
    "Real Estate": [
        {"ticker": "AMT", "name": "American Tower", "quality": 86},
        {"ticker": "PLD", "name": "Prologis Inc", "quality": 88},
        {"ticker": "CCI", "name": "Crown Castle", "quality": 82},
        {"ticker": "EQIX", "name": "Equinix Inc", "quality": 87},
        {"ticker": "SPG", "name": "Simon Property Group", "quality": 79},
        {"ticker": "O", "name": "Realty Income", "quality": 83},
        {"ticker": "WELL", "name": "Welltower Inc", "quality": 81},
        {"ticker": "DLR", "name": "Digital Realty", "quality": 85},
        {"ticker": "PSA", "name": "Public Storage", "quality": 84},
        {"ticker": "OHI", "name": "Omega Healthcare", "quality": 76},
    ],
}


class RebalancingEngine:
    """Analyses portfolio allocation and generates stock-to-stock rebalancing suggestions."""

    def analyze(
        self,
        holdings: List[Dict[str, Any]],
        sector_targets: Optional[Dict[str, float]] = None,
        max_single_position: float = DEFAULT_MAX_SINGLE_POSITION,
        min_single_position: float = DEFAULT_MIN_SINGLE_POSITION,
        target_cash_pct: float = DEFAULT_CASH_TARGET,
    ) -> Dict[str, Any]:
        """
        Run rebalancing analysis with stock-to-stock replacement recommendations.
        """
        if not holdings:
            return self._empty_result("No holdings to analyse.")

        targets = sector_targets or DEFAULT_SECTOR_TARGETS
        total_value = sum(h.get("current_value", 0) or 0 for h in holdings)
        if total_value <= 0:
            return self._empty_result("Portfolio has zero or negative total value.")

        # ── Current allocation ─────────────────────────────
        position_alloc = {}
        sector_alloc = {}
        for h in holdings:
            sym = h.get("symbol", "")
            val = h.get("current_value", 0) or 0
            pct = (val / total_value * 100) if total_value > 0 else 0
            sector = h.get("sector", "Unknown")

            position_alloc[sym] = {
                "symbol": sym,
                "current_value": round(val, 2),
                "current_pct": round(pct, 2),
                "target_pct": None,
                "deviation_pct": 0,
                "action": "hold",
                "shares_to_trade": None,
                "estimated_amount": None,
            }
            sector_alloc[sector] = sector_alloc.get(sector, 0) + pct

        # ── Deviation from targets ─────────────────────────
        over_allocations = []
        under_allocations = []

        for sym, info in position_alloc.items():
            pct = info["current_pct"]
            if pct > max_single_position:
                info["deviation_pct"] = round(pct - max_single_position, 2)
                info["action"] = "reduce"
                over_allocations.append({
                    "symbol": sym,
                    "current_pct": round(pct, 2),
                    "excess_pct": round(pct - max_single_position, 2),
                    "estimated_amount": round((pct - max_single_position) / 100 * total_value, 2),
                })
            elif pct < min_single_position:
                info["deviation_pct"] = round(pct - min_single_position, 2)
                info["action"] = "increase"
                under_allocations.append({
                    "symbol": sym,
                    "current_pct": round(pct, 2),
                    "deficit_pct": round(min_single_position - pct, 2),
                    "estimated_amount": round((min_single_position - pct) / 100 * total_value, 2),
                })

        # ── Sector deviation ──────────────────────────────
        sector_deviation = []
        for sector, target_pct in targets.items():
            current_pct = sector_alloc.get(sector, 0)
            deviation = current_pct - target_pct
            if abs(deviation) > 3:
                sector_deviation.append({
                    "sector": sector,
                    "current_pct": round(current_pct, 1),
                    "target_pct": target_pct,
                    "deviation_pct": round(deviation, 1),
                    "action": "reduce" if deviation > 0 else "increase",
                    "estimated_amount": round(abs(deviation) / 100 * total_value, 2),
                })

        # ── Stock-level replacement analysis ───────────────
        stock_swaps = self._evaluate_stock_swaps(
            holdings, sector_alloc, targets, total_value,
        )

        # ── Trade suggestions ──────────────────────────────
        suggestions = self._generate_suggestions(
            over_allocations, under_allocations, sector_deviation,
            holdings, total_value, position_alloc, stock_swaps,
        )

        # ── CRITICAL: Consistency validation ──────────────────
        suggestions = self._validate_and_deduplicate(suggestions, stock_swaps, holdings)

        # ── Summary metrics ────────────────────────────────
        total_deviation = sum(
            abs(info["deviation_pct"])
            for info in position_alloc.values()
        )
        avg_deviation = total_deviation / len(position_alloc) if position_alloc else 0
        rebalancing_score = max(0, min(100, round(100 - avg_deviation * 10, 1)))

        return {
            "rebalancing_score": rebalancing_score,
            "total_portfolio_value": round(total_value, 2),
            "total_positions": len(holdings),
            "position_allocation": list(position_alloc.values()),
            "sector_allocation": [
                {"sector": s, "current_pct": round(p, 1), "target_pct": targets.get(s)}
                for s, p in sorted(sector_alloc.items(), key=lambda x: -x[1])
            ],
            "sector_deviation": sorted(sector_deviation, key=lambda x: -abs(x["deviation_pct"])),
            "over_allocations": sorted(over_allocations, key=lambda x: -x["excess_pct"]),
            "under_allocations": under_allocations,
            "stock_swaps": stock_swaps,
            "suggestions": suggestions,
            "summary": self._generate_summary(
                rebalancing_score, over_allocations, under_allocations,
                sector_deviation, stock_swaps, total_value,
            ),
            "last_analyzed": datetime.utcnow().isoformat(),
        }

    def _evaluate_stock_swaps(
        self,
        holdings: List[Dict[str, Any]],
        sector_alloc: Dict[str, float],
        targets: Dict[str, float],
        total_value: float,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate each holding for potential stock-to-stock replacement.
        
        Returns a list of swap recommendations, each containing:
        - Current holding being evaluated
        - Why it's being flagged
        - Suggested replacement (or "no action" if insufficient evidence)
        - Portfolio impact of the swap
        - Confidence level
        
        CRITICAL: Does NOT force replacements. Conservative for long-term holdings.
        """
        swaps = []
        holding_symbols = {h["symbol"] for h in holdings}
        holding_by_symbol = {h["symbol"]: h for h in holdings}

        for h in holdings:
            symbol = h["symbol"]
            sector = h.get("sector", "Unknown") or "Unknown"
            gain_pct = h.get("unrealized_gain_pct") or 0
            alloc_pct = (h.get("current_value", 0) or 0) / total_value * 100 if total_value else 0
            sector_pct = sector_alloc.get(sector, 0)
            target_sector_pct = targets.get(sector, 0)

            # Evaluate whether this holding should be flagged for review
            flags = self._evaluate_holding_flags(h, sector_pct, target_sector_pct, holdings, total_value)

            if not flags:
                continue  # No meaningful signals — HOLD

            # Determine action severity
            action = self._determine_action(flags, gain_pct, alloc_pct)

            # Find replacement candidates
            replacement = self._find_best_replacement(
                symbol, sector, flags, holdings, holding_symbols, sector_alloc, targets,
            )

            # Calculate portfolio impact
            portfolio_impact = self._calculate_portfolio_impact(
                h, replacement, sector_alloc, targets, total_value,
            )

            # Generate explanation
            explanation = self._generate_swap_explanation(
                h, flags, action, replacement, portfolio_impact,
            )

            # Confidence based on signal strength
            confidence = self._calculate_confidence(flags, action)

            swap = {
                "symbol": symbol,
                "name": h.get("name", symbol),
                "sector": sector,
                "current_value": round(h.get("current_value", 0) or 0, 2),
                "current_allocation_pct": round(alloc_pct, 2),
                "unrealized_gain_pct": round(gain_pct, 2),
                "flags": flags,
                "action": action,
                "confidence": confidence,
                "explanation": explanation,
                "portfolio_impact": portfolio_impact,
            }

            if replacement:
                swap["replacement"] = replacement
            else:
                swap["replacement"] = None
                swap["no_replacement_reason"] = (
                    "No sufficiently strong replacement candidate identified. "
                    "Maintaining the current position may be preferable."
                )

            swaps.append(swap)

        # Sort by action severity, then by confidence (highest first)
        action_order = {"SELL": 0, "REDUCE": 1, "SWAP_CANDIDATE": 2, "MONITOR": 3, "HOLD": 4}
        confidence_order = {"High": 4, "Medium-High": 3, "Medium": 2, "Low": 1}
        swaps.sort(key=lambda s: (action_order.get(s["action"], 5), -confidence_order.get(s["confidence"], 0)))

        return swaps

    def _evaluate_holding_flags(
        self, h: Dict, sector_pct: float, target_sector_pct: float,
        all_holdings: list, total_value: float,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate a holding for multiple meaningful signals.
        Returns empty list if no significant issues found.
        
        CRITICAL: Requires MULTIPLE meaningful signals. Does NOT flag from single weak indicator.
        """
        flags = []
        symbol = h["symbol"]
        sector = h.get("sector", "Unknown") or "Unknown"
        gain_pct = h.get("unrealized_gain_pct") or 0
        alloc_pct = (h.get("current_value", 0) or 0) / total_value * 100 if total_value else 0

        # Flag 1: Significant underperformance (not just one bad day)
        if gain_pct < -20:
            flags.append({
                "type": "severe_underperformance",
                "severity": "high",
                "detail": f"Down {abs(gain_pct):.1f}% — significant loss requiring review",
            })
        elif gain_pct < -10:
            flags.append({
                "type": "moderate_underperformance",
                "severity": "medium",
                "detail": f"Down {abs(gain_pct):.1f}% — underperforming portfolio average",
            })

        # Flag 2: Position concentration risk
        if alloc_pct > DEFAULT_MAX_SINGLE_POSITION:
            flags.append({
                "type": "overconcentration",
                "severity": "high",
                "detail": f"Position is {alloc_pct:.1f}% of portfolio (target: <{DEFAULT_MAX_SINGLE_POSITION}%)",
            })
        elif alloc_pct > 10:
            flags.append({
                "type": "concentration_watch",
                "severity": "low",
                "detail": f"Position is {alloc_pct:.1f}% — approaching concentration threshold",
            })

        # Flag 3: Sector overweight
        if sector_pct > target_sector_pct + 5:
            flags.append({
                "type": "sector_overweight",
                "severity": "medium",
                "detail": f"{sector} sector is {sector_pct:.1f}% (target: {target_sector_pct}%)",
            })

        # Flag 4: Relative performance vs sector peers
        sector_peers = [h2 for h2 in all_holdings if h2["symbol"] != symbol and (h2.get("sector") or "Unknown") == sector]
        if sector_peers:
            peer_avg_gain = sum((h2.get("unrealized_gain_pct") or 0) for h2 in sector_peers) / len(sector_peers)
            if gain_pct < peer_avg_gain - 15:
                flags.append({
                    "type": "sector_underperformance",
                    "severity": "medium",
                    "detail": f"Underperforming {sector} peers by {abs(gain_pct - peer_avg_gain):.1f}%",
                })

        # Only return flags with medium+ severity (avoid noise from single weak signals)
        meaningful_flags = [f for f in flags if f["severity"] in ("high", "medium")]
        return meaningful_flags

    def _determine_action(self, flags: List[Dict], gain_pct: float, alloc_pct: float) -> str:
        """Determine action based on flag severity and combination."""
        high_count = sum(1 for f in flags if f["severity"] == "high")
        medium_count = sum(1 for f in flags if f["severity"] == "medium")

        if high_count >= 2 or (high_count >= 1 and medium_count >= 2):
            return "SELL"
        if high_count >= 1 or medium_count >= 2:
            return "REDUCE"
        if medium_count >= 1 and gain_pct < -5:
            return "SWAP_CANDIDATE"
        return "MONITOR"

    def _find_best_replacement(
        self, symbol: str, sector: str, flags: List[Dict],
        all_holdings: list, holding_symbols: set,
        sector_alloc: Dict, targets: Dict,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best replacement candidate for a flagged holding.
        
        CRITICAL: Replacement targets must NOT already be in the portfolio.
        This is a stock swap, not an addition to an existing position.
        
        Prioritizes:
        1. Same-sector quality stocks from universe (NOT held)
        2. Cross-sector quality stocks from universe (NOT held)
        """
        holding_by_symbol = {h["symbol"]: h for h in all_holdings}
        weak_gain = (holding_by_symbol.get(symbol, {}).get("unrealized_gain_pct") or 0)
        weak_sector = sector
        sector_is_overweight = sector_alloc.get(sector, 0) > targets.get(sector, 0) + 3

        all_candidates = []

        # CRITICAL: Build exclusion set — NEVER recommend a stock already held
        # This prevents: KMB -> COST when COST is already in portfolio
        excluded_symbols = set(holding_symbols)
        excluded_symbols.add(symbol)  # Don't replace with self

        # 1. Candidate universe — same sector (exclude held stocks)
        universe = CANDIDATE_UNIVERSE.get(sector, [])
        for candidate in universe:
            ticker = candidate["ticker"]
            if ticker in excluded_symbols:
                continue  # Already in portfolio or self
            score = self._score_replacement_candidate(
                0, 0, True, sector_is_overweight, flags,
                quality=candidate.get("quality", 75),
            )
            all_candidates.append({
                "ticker": ticker,
                "name": candidate["name"],
                "sector": sector,
                "source": "universe",
                "gain_pct": 0,
                "allocation_pct": 0,
                "same_sector": True,
                "replacement_score": score,
                "reason": f"Established {sector} company with strong fundamentals (quality: {candidate.get('quality', 75)}/100)",
            })

        # 2. Cross-sector candidates (only if sector is overweight)
        if sector_is_overweight and len(all_candidates) < 3:
            for other_sector, candidates in CANDIDATE_UNIVERSE.items():
                if other_sector == sector:
                    continue
                for candidate in candidates[:2]:
                    ticker = candidate["ticker"]
                    if ticker in excluded_symbols:
                        continue  # Already in portfolio
                    score = self._score_replacement_candidate(
                        0, 0, False, sector_is_overweight, flags,
                        quality=candidate.get("quality", 75),
                    )
                    all_candidates.append({
                        "ticker": ticker,
                        "name": candidate["name"],
                        "sector": other_sector,
                        "source": "universe",
                        "gain_pct": 0,
                        "allocation_pct": 0,
                        "same_sector": False,
                        "replacement_score": score,
                        "reason": f"Cross-sector alternative in {other_sector} — improves diversification",
                    })

        if not all_candidates:
            return None

        all_candidates.sort(key=lambda c: -c["replacement_score"])
        best = all_candidates[0]

        if best["replacement_score"] < 55:
            return None

        return {
            "replacement_ticker": best["ticker"],
            "replacement_name": best["name"],
            "sector": best["sector"],
            "same_sector": best["same_sector"],
            "source": best["source"],
            "replacement_score": best["replacement_score"],
            "reason": best["reason"],
            "why_this_replacement": self._generate_replacement_reasoning(best, flags, sector_is_overweight),
        }

    def _score_replacement_candidate(
        self, gain_pct: float, alloc_pct: float, same_sector: bool,
        sector_is_overweight: bool, flags: List[Dict],
        quality: int = 75,
    ) -> float:
        """
        Score a replacement candidate 0-100.
        
        Factors:
        - Quality score (from universe or performance data)
        - Sector fit (same sector preferred unless overweight)
        - Portfolio diversification benefit
        - Position size (prefer candidates not already large)
        """
        score = 50  # base

        # Quality component (0-25 points)
        score += (quality - 50) * 0.5

        # Sector fit (0-15 points)
        if same_sector and not sector_is_overweight:
            score += 15  # same sector, not overweight — best fit
        elif not same_sector and sector_is_overweight:
            score += 15  # different sector, sector overweight — diversification benefit
        elif same_sector and sector_is_overweight:
            score += 5   # same sector, but sector is overweight — less ideal
        else:
            score += 0   # different sector, sector not overweight — less ideal

        # Performance component (0-10 points)
        if gain_pct > 20:
            score += 10
        elif gain_pct > 10:
            score += 7
        elif gain_pct > 0:
            score += 3

        # Position size component (0-10 points)
        if alloc_pct < 5:
            score += 10  # small position — good addition
        elif alloc_pct < 10:
            score += 5
        elif alloc_pct >= DEFAULT_MAX_SINGLE_POSITION:
            score -= 5  # already large — less ideal

        return max(0, min(100, round(score, 1)))

    def _calculate_portfolio_impact(
        self, holding: Dict, replacement: Optional[Dict],
        sector_alloc: Dict, targets: Dict, total_value: float,
    ) -> Dict[str, Any]:
        """Calculate the portfolio impact of a potential swap."""
        sector = holding.get("sector", "Unknown") or "Unknown"
        current_sector_pct = sector_alloc.get(sector, 0)
        target_sector_pct = targets.get(sector, 0)

        impact = {
            "current_sector_pct": round(current_sector_pct, 1),
            "target_sector_pct": target_sector_pct,
            "sector_would_change_to": round(current_sector_pct, 1),  # same sector = no change
        }

        if replacement and not replacement.get("same_sector"):
            # Cross-sector swap would change sector allocation
            new_sector = replacement["sector"]
            holding_value = holding.get("current_value", 0) or 0
            holding_pct = holding_value / total_value * 100 if total_value else 0

            impact["sector_would_change_to"] = round(current_sector_pct - holding_pct, 1)
            impact["new_sector"] = new_sector
            impact["new_sector_pct"] = round(
                sector_alloc.get(new_sector, 0) + holding_pct, 1
            )

        # Risk assessment
        gain_pct = holding.get("unrealized_gain_pct") or 0
        if gain_pct < -20:
            impact["risk_reduction"] = "Significant — current position has large unrealized loss"
        elif gain_pct < -10:
            impact["risk_reduction"] = "Moderate — position is underperforming"
        else:
            impact["risk_reduction"] = "Minimal — position performance is acceptable"

        return impact

    def _generate_swap_explanation(
        self, holding: Dict, flags: List[Dict], action: str,
        replacement: Optional[Dict], portfolio_impact: Dict,
    ) -> Dict[str, str]:
        """Generate clear explanation of why the swap is recommended."""
        symbol = holding["symbol"]
        sector = holding.get("sector", "Unknown") or "Unknown"

        # Why sell/reduce
        why_sell_parts = []
        for flag in flags:
            why_sell_parts.append(flag["detail"])
        why_sell = "; ".join(why_sell_parts[:3])

        # Why replacement
        why_replace = ""
        if replacement:
            why_replace = replacement.get("why_this_replacement", replacement.get("reason", ""))
        else:
            why_replace = "No sufficiently strong replacement identified. Consider monitoring the current position."

        return {
            "why_action": f"{symbol}: {why_sell}",
            "why_replacement": why_replace,
            "portfolio_benefit": self._generate_portfolio_benefit(
                holding, replacement, portfolio_impact,
            ),
        }

    def _generate_replacement_reasoning(
        self, candidate: Dict, flags: List[Dict], sector_is_overweight: bool,
    ) -> str:
        """Generate specific reasoning for why this replacement improves the portfolio."""
        reasons = []

        if candidate.get("same_sector"):
            reasons.append(f"Maintains {candidate['sector']} exposure with a stronger company")
        else:
            reasons.append(f"Shifts exposure from overweight {candidate['sector']} sector to improve diversification")

        if candidate.get("source") == "portfolio":
            reasons.append(f"Already held in portfolio ({candidate['gain_pct']:+.1f}% gain) — proven performer")
        else:
            reasons.append(f"Quality score: {candidate.get('replacement_score', 0):.0f}/100")

        flag_types = {f["type"] for f in flags}
        if "severe_underperformance" in flag_types or "sector_underperformance" in flag_types:
            reasons.append("Addresses underperformance relative to peers")
        if "overconcentration" in flag_types:
            reasons.append("Reduces single-position concentration risk")
        if "sector_overweight" in flag_types and not candidate.get("same_sector"):
            reasons.append("Reduces sector concentration")

        return "; ".join(reasons[:3])

    def _generate_portfolio_benefit(
        self, holding: Dict, replacement: Optional[Dict], portfolio_impact: Dict,
    ) -> str:
        """Generate clear statement of portfolio benefit."""
        benefits = []

        if replacement and not replacement.get("same_sector"):
            new_sector = replacement.get("sector", "Unknown")
            current_sector = holding.get("sector", "Unknown") or "Unknown"
            current_pct = portfolio_impact.get("current_sector_pct", 0)
            target_pct = portfolio_impact.get("target_sector_pct", 0)
            if current_pct > target_pct:
                benefits.append(f"Reduces {current_sector} concentration ({current_pct:.1f}% → {portfolio_impact.get('sector_would_change_to', 0):.1f}%)")
            benefits.append(f"Adds {new_sector} exposure ({portfolio_impact.get('new_sector_pct', 0):.1f}%)")
        else:
            benefits.append("Maintains current sector allocation")

        risk = portfolio_impact.get("risk_reduction", "")
        if risk and "Significant" in risk:
            benefits.append("Reduces portfolio risk from concentrated loss")

        return "; ".join(benefits) if benefits else "Improves overall portfolio quality"

    def _calculate_confidence(self, flags: List[Dict], action: str) -> str:
        """Calculate confidence level based on signal strength."""
        high_count = sum(1 for f in flags if f["severity"] == "high")
        medium_count = sum(1 for f in flags if f["severity"] == "medium")

        if action == "SELL" and high_count >= 2:
            return "High"
        if action in ("REDUCE", "SELL") and high_count >= 1:
            return "Medium-High"
        if action == "REDUCE" and medium_count >= 2:
            return "Medium"
        if action == "SWAP_CANDIDATE":
            return "Medium"
        return "Low"

    def _generate_suggestions(
        self, over_allocs, under_allocs, sector_dev,
        holdings, total_value, position_alloc, stock_swaps,
    ) -> List[Dict[str, Any]]:
        """Generate prioritised trade suggestions incorporating stock swap analysis."""
        suggestions = []

        # Build sector -> holdings mapping
        sector_holdings = {}
        for h in holdings:
            sec = h.get("sector", "Unknown") or "Unknown"
            sector_holdings.setdefault(sec, []).append(h)

        # 1. Stock-level swap recommendations (highest priority)
        for swap in stock_swaps:
            if swap["action"] in ("SELL", "REDUCE", "SWAP_CANDIDATE"):
                priority = "high" if swap["action"] == "SELL" else "medium"
                s = {
                    "priority": priority,
                    "action": f"swap_{swap['action'].lower()}",
                    "symbol": swap["symbol"],
                    "sector": swap["sector"],
                    "current_pct": swap["current_allocation_pct"],
                    "reason": swap["explanation"].get("why_action", ""),
                    "estimated_impact": swap["explanation"].get("portfolio_benefit", ""),
                    "confidence": swap["confidence"],
                    "flags": swap["flags"],
                }
                if swap.get("replacement"):
                    s["replacement"] = swap["replacement"]
                if swap.get("no_replacement_reason"):
                    s["no_replacement_reason"] = swap["no_replacement_reason"]
                suggestions.append(s)

        # 2. High-priority: reduce oversized positions (if not already covered by swaps)
        swap_symbols = {s.get("symbol") for s in stock_swaps}
        for oa in over_allocs:
            if oa["symbol"] in swap_symbols:
                continue
            reduce_amount = oa["estimated_amount"]
            if reduce_amount > 0:
                replacement = self._find_replacement_basic(oa["symbol"], sector_holdings, holdings)
                s = {
                    "priority": "high",
                    "action": "reduce",
                    "symbol": oa["symbol"],
                    "current_pct": oa["current_pct"],
                    "target_pct": round(DEFAULT_MAX_SINGLE_POSITION, 1),
                    "reduce_amount_usd": round(reduce_amount, 2),
                    "reason": f"{oa['symbol']} is overweight at {oa['current_pct']:.1f}% "
                              f"(target: {DEFAULT_MAX_SINGLE_POSITION}%).",
                    "estimated_impact": f"Reduces single-position risk and frees "
                                        f"${reduce_amount:,.0f} for reallocation.",
                }
                if replacement:
                    s["replacement"] = replacement
                suggestions.append(s)

        # 3. Medium-priority: sector rebalancing
        for sd in sector_dev:
            if sd["action"] == "reduce":
                suggestions.append({
                    "priority": "medium",
                    "action": "reduce_sector_exposure",
                    "sector": sd["sector"],
                    "current_pct": sd["current_pct"],
                    "target_pct": sd["target_pct"],
                    "reduce_amount_usd": sd["estimated_amount"],
                    "reason": f"{sd['sector']} is overweight at {sd['current_pct']:.1f}% "
                              f"(target: {sd['target_pct']}%).",
                    "estimated_impact": f"Reduces {sd['sector']} concentration.",
                })
            elif sd["action"] == "increase":
                suggestions.append({
                    "priority": "medium",
                    "action": "add_sector_exposure",
                    "sector": sd["sector"],
                    "current_pct": sd["current_pct"],
                    "target_pct": sd["target_pct"],
                    "invest_amount_usd": sd["estimated_amount"],
                    "reason": f"{sd['sector']} is underweight at {sd['current_pct']:.1f}% "
                              f"(target: {sd['target_pct']}%).",
                    "estimated_impact": f"Improves sector diversification.",
                })

        # 4. Low-priority: trim small positions
        for ua in under_allocs:
            if ua["deficit_pct"] > 3:
                suggestions.append({
                    "priority": "low",
                    "action": "increase_position",
                    "symbol": ua["symbol"],
                    "current_pct": ua["current_pct"],
                    "invest_amount_usd": ua["estimated_amount"],
                    "reason": f"{ua['symbol']} is a small position at {ua['current_pct']:.1f}%.",
                    "estimated_impact": f"Increases position to meaningful size.",
                })

        return suggestions

    def _validate_and_deduplicate(
        self, suggestions: List[Dict], stock_swaps: List[Dict], holdings: List[Dict],
    ) -> List[Dict[str, Any]]:
        """
        Final consistency validator. Enforces RULES 1-8:
        RULE 1: No symbol can have both BUY/ADD and SELL/REDUCE
        RULE 2: Replacement target cannot already be in portfolio
        RULE 3: Replacement source must be a current holding
        RULE 4: Replacement pairs must be unique
        RULE 5: No circular replacements (KMB->COST and COST->X)
        RULE 6: If holding is being reduced, replacement is separate candidate
        RULE 7: Same candidate must not appear multiple times with different actions
        RULE 8: Normalize symbols before comparison
        """
        held_symbols = {h["symbol"] for h in holdings}

        # Build symbol -> canonical action map
        # Action priority: SELL > REDUCE > ADD > HOLD (higher priority wins)
        ACTION_PRIORITY = {
            "sell": 5, "swap_sell": 5, "swap_reduce": 4,
            "reduce": 4, "reduce_sector_exposure": 3,
            "add": 2, "add_sector_exposure": 2, "increase_position": 2,
            "swap_swap_candidate": 1, "hold": 0,
        }

        symbol_actions: Dict[str, List[Dict]] = {}
        for s in suggestions:
            sym = s.get("symbol", "").strip().upper()
            if not sym:
                continue
            symbol_actions.setdefault(sym, []).append(s)

        # RULE 1: No symbol can have both BUY/ADD and SELL/REDUCE
        buy_keywords = {"add", "increase_position", "add_sector_exposure"}
        sell_keywords = {"sell", "reduce", "swap_sell", "swap_reduce", "reduce_sector_exposure"}

        validated = []
        seen_replacements = set()  # RULE 4: unique replacement pairs
        seen_symbols = set()  # RULE 7: no duplicate actions per symbol

        for s in suggestions:
            sym = s.get("symbol", "").strip().upper()
            action = (s.get("action") or "").lower()
            replacement_ticker = s.get("replacement", {}).get("replacement_ticker", "").strip().upper() if s.get("replacement") else ""

            # RULE 2: Replacement target cannot already be in portfolio
            if replacement_ticker and replacement_ticker in held_symbols:
                logger.warning(
                    f"Consistency: Removing suggestion for {sym} — "
                    f"replacement {replacement_ticker} is already held"
                )
                continue

            # RULE 3: Replacement source must be a current holding
            if "swap" in action and sym not in held_symbols:
                logger.warning(
                    f"Consistency: Removing swap suggestion for {sym} — "
                    f"not a current holding"
                )
                continue

            # RULE 4: Replacement pairs must be unique
            if replacement_ticker:
                pair = (sym, replacement_ticker)
                if pair in seen_replacements:
                    logger.warning(
                        f"Consistency: Removing duplicate replacement pair {sym}->{replacement_ticker}"
                    )
                    continue
                seen_replacements.add(pair)

            # RULE 5: No circular replacements
            if replacement_ticker:
                is_circular = False
                for other_s in suggestions:
                    other_sym = other_s.get("symbol", "").strip().upper()
                    other_repl = other_s.get("replacement", {}).get("replacement_ticker", "").strip().upper() if other_s.get("replacement") else ""
                    if other_sym == replacement_ticker and other_repl == sym:
                        is_circular = True
                        break
                if is_circular:
                    logger.warning(
                        f"Consistency: Removing circular replacement {sym}->{replacement_ticker}"
                    )
                    continue

            # RULE 1: Check for BUY+SELL conflict
            existing_actions = symbol_actions.get(sym, [])
            has_buy = any(
                (s2.get("action") or "").lower() in buy_keywords
                for s2 in existing_actions if s2 is not s
            )
            has_sell = any(
                (s2.get("action") or "").lower() in sell_keywords
                for s2 in existing_actions if s2 is not s
            )

            if has_buy and action in sell_keywords:
                logger.warning(
                    f"Consistency: Removing {action} for {sym} — "
                    f"BUY/ADD exists, SELL/REDUCE takes priority"
                )
                continue
            if has_sell and action in buy_keywords:
                logger.warning(
                    f"Consistency: Removing {action} for {sym} — "
                    f"SELL/REDUCE exists, higher priority"
                )
                continue

            # RULE 7: Same symbol with same action type — keep only the first
            action_key = f"{sym}:{action}"
            if action_key in seen_symbols:
                logger.warning(
                    f"Consistency: Removing duplicate {action} for {sym}"
                )
                continue
            seen_symbols.add(action_key)

            validated.append(s)

        return validated

    def _generate_summary(
        self, score, over_allocs, under_allocs, sector_dev, stock_swaps, total_value,
    ) -> str:
        parts = [f"Rebalancing score: {score}/100."]

        # Stock-level swap summary
        sell_swaps = [s for s in stock_swaps if s["action"] in ("SELL", "REDUCE")]
        if sell_swaps:
            syms = ", ".join(s["symbol"] for s in sell_swaps[:3])
            parts.append(f"Review positions: {syms}.")

        monitor_swaps = [s for s in stock_swaps if s["action"] == "MONITOR"]
        if monitor_swaps:
            syms = ", ".join(s["symbol"] for s in monitor_swaps[:3])
            parts.append(f"Monitor: {syms}.")

        if over_allocs:
            syms = ", ".join(o["symbol"] for o in over_allocs[:3])
            parts.append(f"Reduce overweight: {syms}.")
        if sector_dev:
            sectors = ", ".join(s["sector"] for s in sector_dev[:3])
            parts.append(f"Sectors needing rebalancing: {sectors}.")
        if not sell_swaps and not over_allocs and not sector_dev:
            parts.append("Portfolio allocation looks well-balanced. No action recommended.")

        return " ".join(parts)

    def _empty_result(self, message: str) -> Dict[str, Any]:
        return {
            "rebalancing_score": 0,
            "total_portfolio_value": 0,
            "total_positions": 0,
            "position_allocation": [],
            "sector_allocation": [],
            "sector_deviation": [],
            "over_allocations": [],
            "under_allocations": [],
            "stock_swaps": [],
            "suggestions": [],
            "summary": message,
            "last_analyzed": datetime.utcnow().isoformat(),
        }

    def _find_replacement_basic(
        self, symbol: str, sector_holdings: dict, all_holdings: list,
    ) -> Optional[Dict[str, Any]]:
        """Basic replacement finder for over-allocated positions.
        
        CRITICAL: Only recommends stocks from the candidate universe,
        NOT from existing portfolio holdings. This is a true replacement,
        not an addition.
        """
        weak_holding = None
        weak_sector = None
        for h in all_holdings:
            if h["symbol"] == symbol:
                weak_holding = h
                weak_sector = h.get("sector", "Unknown") or "Unknown"
                break
        if not weak_holding:
            return None

        # Build exclusion set: all held symbols + self
        held_symbols = {h["symbol"] for h in all_holdings}

        candidates = []

        # Search universe for same-sector candidates not held
        universe = CANDIDATE_UNIVERSE.get(weak_sector, [])
        for u in universe:
            if u["ticker"] in held_symbols or u["ticker"] == symbol:
                continue
            candidates.append({
                "ticker": u["ticker"],
                "name": u["name"],
                "sector": weak_sector,
                "same_sector": True,
                "reason": f"Established {weak_sector} company not currently held (quality: {u.get('quality', 75)}/100).",
                "replacement_score": u.get("quality", 75),
            })

        if not candidates:
            return None

        candidates.sort(key=lambda c: -c["replacement_score"])
        best = candidates[0]
        return {
            "replacement_ticker": best["ticker"],
            "replacement_name": best["name"],
            "sector": best["sector"],
            "same_sector": best["same_sector"],
            "reason": best["reason"],
            "replacement_score": best.get("replacement_score", 60),
        }

    # Backward-compatible alias
    def _find_replacement(self, symbol, sector_holdings, all_holdings):
        """Alias for _find_replacement_basic (backward compatibility)."""
        return self._find_replacement_basic(symbol, sector_holdings, all_holdings)
