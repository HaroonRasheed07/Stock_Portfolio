"""
Diversification analysis engine.
Analyzes position concentration, sector exposure, correlation, and ETF overlap.
"""
import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DiversificationEngine:
    """Analyzes portfolio diversification quality."""

    def analyze(
        self,
        holdings: List[Dict[str, Any]],
        historical_data: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> Dict[str, Any]:
        """Run full diversification analysis."""
        if not holdings:
            return {
                "score": 0, "level": "Critical",
                "explanation": "No holdings to analyze.",
                "warnings": [], "recommendations": [],
            }

        total_value = sum(h.get("current_value", 0) or 0 for h in holdings)
        if total_value == 0:
            return {"score": 0, "level": "Critical", "warnings": ["Portfolio has no value data"]}

        # ── Position Concentration ───────────────────────
        position_weights = {}
        for h in holdings:
            w = (h.get("current_value", 0) or 0) / total_value * 100
            position_weights[h["symbol"]] = round(w, 2)

        high_concentration = [
            {"symbol": sym, "weight": w}
            for sym, w in position_weights.items() if w > 15
        ]
        high_concentration.sort(key=lambda x: -x["weight"])

        # HHI for position concentration
        hhi = sum((w/100)**2 for w in position_weights.values())
        n = len(holdings)
        min_hhi = 1/n if n > 0 else 1
        position_score = max(0, 100 - ((hhi - min_hhi) / (1 - min_hhi) * 100)) if n > 1 else 0

        # ── Sector Allocation ────────────────────────────
        sector_allocation = {}
        for h in holdings:
            sector = h.get("sector") or "Unknown"
            value = h.get("current_value", 0) or 0
            sector_allocation[sector] = sector_allocation.get(sector, 0) + value / total_value * 100

        sector_allocation = {k: round(v, 2) for k, v in sorted(sector_allocation.items(), key=lambda x: -x[1])}

        # Sector concentration score
        num_sectors = len([s for s in sector_allocation if s != "Unknown"])
        if num_sectors >= 8:
            sector_score = 90
        elif num_sectors >= 5:
            sector_score = 70
        elif num_sectors >= 3:
            sector_score = 50
        else:
            sector_score = 20

        # Penalize dominant sector
        if sector_allocation:
            max_sector_weight = max(sector_allocation.values())
            if max_sector_weight > 40:
                sector_score -= 20
            elif max_sector_weight > 30:
                sector_score -= 10

        # ── Asset Type Allocation ────────────────────────
        asset_allocation = {}
        for h in holdings:
            atype = h.get("asset_type", "stock") or "stock"
            value = h.get("current_value", 0) or 0
            asset_allocation[atype] = asset_allocation.get(atype, 0) + value / total_value * 100
        asset_allocation = {k: round(v, 2) for k, v in asset_allocation.items()}

        # ── Correlation Analysis ─────────────────────────
        correlated_pairs = []
        correlation_score = 70  # default if no data

        if historical_data and len(historical_data) >= 2:
            try:
                returns = {}
                for symbol, df in historical_data.items():
                    if not df.empty and len(df) > 30:
                        close = df["Close"].astype(float)
                        returns[symbol] = close.pct_change().dropna()

                if len(returns) >= 2:
                    returns_df = pd.DataFrame(returns).dropna()
                    if len(returns_df) >= 20:
                        corr = returns_df.corr()
                        for i in range(len(corr)):
                            for j in range(i+1, len(corr)):
                                c = corr.iloc[i, j]
                                if c > 0.7:
                                    correlated_pairs.append({
                                        "pair": [corr.index[i], corr.columns[j]],
                                        "correlation": round(float(c), 3),
                                    })

                        # Average correlation
                        upper = []
                        for i in range(len(corr)):
                            for j in range(i+1, len(corr)):
                                upper.append(corr.iloc[i, j])
                        avg_corr = np.mean(upper)
                        correlation_score = max(0, 100 - float(avg_corr) * 100)

                        correlated_pairs.sort(key=lambda x: -x["correlation"])
            except Exception as e:
                logger.warning(f"Correlation analysis error: {e}")

        # ── ETF Overlap Detection ────────────────────────
        etf_warnings = []
        etf_holdings = [h for h in holdings if h.get("asset_type") == "etf"]
        stock_holdings = [h["symbol"] for h in holdings if h.get("asset_type") != "etf"]

        # Known major ETF components for overlap detection
        broad_etfs = {"VOO", "SPY", "IVV", "VTI", "QQQ"}
        div_etfs = {"VYM", "SCHD", "DVY", "HDV"}

        for etf in etf_holdings:
            sym = etf["symbol"]
            if sym in broad_etfs:
                # Broad market ETFs overlap with large-cap stocks
                overlapping = [s for s in stock_holdings
                               if s in {"AAPL", "MSFT", "GOOG", "GOOGL", "AMZN", "NVDA",
                                        "META", "BRK.B", "JPM", "JNJ", "V", "UNH", "PG",
                                        "HD", "MA", "COST", "ABBV", "PEP", "KO", "MRK",
                                        "CSCO", "TXN", "LOW"}]
                if overlapping:
                    etf_warnings.append(
                        f"{sym} (S&P 500 ETF) overlaps with your individual holdings: {', '.join(overlapping[:5])}"
                    )

        # ── Warnings ─────────────────────────────────────
        warnings = []
        recommendations = []

        for hc in high_concentration:
            warnings.append(f"{hc['symbol']} represents {hc['weight']:.1f}% of portfolio — high concentration risk")
            recommendations.append(f"Consider reducing {hc['symbol']} position to below 10-15% of portfolio")

        if num_sectors < 3:
            warnings.append("Portfolio is concentrated in very few sectors")
            recommendations.append("Consider adding holdings in underrepresented sectors")

        if sector_allocation:
            for sector, weight in sector_allocation.items():
                if weight > 35 and sector != "Unknown":
                    warnings.append(f"{sector} sector represents {weight:.1f}% of portfolio")

        for pair in correlated_pairs[:3]:
            warnings.append(f"{pair['pair'][0]} and {pair['pair'][1]} have high correlation ({pair['correlation']:.2f})")

        warnings.extend(etf_warnings)

        if n < 10:
            recommendations.append(f"Portfolio has only {n} holdings — consider adding more for better diversification")
        elif n > 40:
            recommendations.append(f"Portfolio has {n} holdings — consider consolidating to maintain focus")

        # ── Overall Score ────────────────────────────────
        overall = (
            position_score * 0.35 +
            sector_score * 0.30 +
            correlation_score * 0.20 +
            (min(n, 25) / 25 * 100) * 0.15
        )
        overall = max(0, min(100, overall))

        if overall >= 80:
            level = "Excellent"
        elif overall >= 60:
            level = "Good"
        elif overall >= 40:
            level = "Moderate"
        elif overall >= 20:
            level = "Poor"
        else:
            level = "Critical"

        explanation = self._generate_explanation(
            overall, level, n, position_weights, sector_allocation,
            high_concentration, correlated_pairs, warnings
        )

        return {
            "score": round(overall, 1),
            "level": level,
            "position_concentration": position_weights,
            "sector_allocation": sector_allocation,
            "asset_type_allocation": asset_allocation,
            "high_concentration_positions": high_concentration,
            "correlated_pairs": correlated_pairs[:5],
            "warnings": warnings,
            "recommendations": recommendations,
            "explanation": explanation,
        }

    def _generate_explanation(
        self, score, level, n, positions, sectors,
        high_conc, corr_pairs, warnings
    ) -> str:
        parts = [f"Portfolio diversification is rated {level} with a score of {score:.0f}/100."]
        parts.append(f"The portfolio contains {n} holdings across {len([s for s in sectors if s != 'Unknown'])} sectors.")

        if high_conc:
            parts.append(f"Warning: {len(high_conc)} position(s) exceed 15% concentration.")

        if corr_pairs:
            parts.append(f"{len(corr_pairs)} pair(s) of holdings have high correlation (>0.7).")

        if score >= 70:
            parts.append("Overall, the portfolio is reasonably well-diversified.")
        elif score >= 40:
            parts.append("There is room to improve diversification by addressing concentration risks.")
        else:
            parts.append("The portfolio has significant diversification concerns that should be addressed.")

        return " ".join(parts)
