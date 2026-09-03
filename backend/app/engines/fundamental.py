"""
Fundamental analysis engine.
Scores companies on financial health, growth, valuation, and quality metrics.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _ensure_decimal_percentage(value: Optional[float]) -> Optional[float]:
    """
    Normalize percentage values to decimal form (0.03 = 3%, not 3 = 3%).

    yfinance returns different formats for different metrics:
    - dividend_yield: 0-1 decimal (0.03 = 3%)
    - peg_ratio: 0-100 decimal (1.5 = 1.5)
    - profit_margin: 0-1 decimal (0.15 = 15%)
    - debt_to_equity: 0-1000+ decimal (0.8 = 80%, 1.5 = 150%)
    - roe/roa: 0-1 decimal (0.15 = 15%)
    - revenue_growth: 0-1 decimal (0.20 = 20%)

    This function normalizes percentage metrics (0-1 range) to verify they're in
    decimal form. If a value is unexpectedly large (like 34 instead of 0.34 for
    dividend yield), it's likely already in percentage form or an error.

    Rule: If the value > 100, it's either:
    - Already in percentage form (e.g., 340 for 340%)
    - An error (e.g., 34000 for what should be 0.34)
    - A valid large number for things like debt_to_equity

    Conservative approach: for dividend yield and margins, cap at reasonable ranges.
    """
    if value is None:
        return None

    # Be conservative: extreme values (< 0 or > 1000) are likely errors
    if value < -1000 or value > 10000:
        logger.warning(f"Suspiciously large value: {value} — may be data error")
        return None

    return value


def _percentage_to_display(value: Optional[float], metric_type: str = "generic") -> Optional[float]:
    """
    Convert a value to display percentage form.

    metric_type guides the conversion:
    - "generic": if 0-1, multiply by 100; if > 100, divide by 100 (safer assumption)
    - "dividend": dividend_yield is always 0-1 decimal; multiply by 100
    - "growth": growth rates are 0-1 decimal; multiply by 100
    - "roe_roa": returns on equity/assets are 0-1 decimal; multiply by 100
    - "margin": profit/operating/gross margins are 0-1 decimal; multiply by 100
    - "pe_ratio": P/E ratios are real numbers (not percentages); don't multiply
    - "debt_to_equity": can be 0.8 (80%) or 2.5 (250%); always multiply by 100
    """
    if value is None:
        return None

    # Metrics that should NOT be converted (already in correct form)
    if metric_type in ("pe_ratio", "peg_ratio", "price_to_sales", "price_to_book", "ev_to_ebitda", "beta"):
        return value

    # Metrics that are always 0-1 decimal and need to be multiplied by 100
    if metric_type in ("dividend", "growth", "roe_roa", "margin", "debt_to_equity"):
        if abs(value) < 100:  # 0-1 range (or small negatives)
            return value * 100
        # If > 100, it's suspicious but could be a data error. Log and return as-is
        logger.warning(f"Unexpected large value for {metric_type}: {value}")
        return value

    # Generic: use heuristic
    if abs(value) < 100:
        return value * 100
    # Already in percentage form or very large number; don't multiply
    return value


class FundamentalEngine:
    """Scores and grades companies based on fundamental metrics."""

    def analyze(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run fundamental analysis on stock info data.
        Returns score (0-100), grade, strengths, weaknesses, and explanation.
        """
        if not info or info.get("error"):
            name = (info or {}).get("name") or (info or {}).get("symbol") or "This security"
            return {
                "score": 50,
                "grade": "Insufficient Data",
                "strengths": [],
                "weaknesses": [],
                "explanation": f"Fundamental data is unavailable for {name}. The score is shown as a neutral "
                               "50 (unknown), not an assessment of quality.",
                "metrics": {},
            }

        scores = {}
        strengths = []
        weaknesses = []
        metrics = {}
        data_points = 0

        # ── Revenue & Growth (15%) ───────────────────────
        revenue_growth = info.get("revenue_growth")
        if revenue_growth is not None:
            revenue_growth = _ensure_decimal_percentage(revenue_growth)
            if revenue_growth is not None:
                data_points += 1
                rg_pct = _percentage_to_display(revenue_growth, "growth")
                metrics["revenue_growth"] = round(rg_pct, 1)
                if rg_pct > 20:
                    scores["revenue_growth"] = 95
                    strengths.append(f"Strong revenue growth of {rg_pct:.1f}%")
                elif rg_pct > 10:
                    scores["revenue_growth"] = 80
                    strengths.append(f"Healthy revenue growth of {rg_pct:.1f}%")
                elif rg_pct > 0:
                    scores["revenue_growth"] = 60
                elif rg_pct > -5:
                    scores["revenue_growth"] = 40
                    weaknesses.append(f"Flat/declining revenue ({rg_pct:.1f}%)")
                else:
                    scores["revenue_growth"] = 20
                    weaknesses.append(f"Revenue declining at {rg_pct:.1f}%")

        # ── Earnings & EPS (15%) ─────────────────────────
        eps = info.get("eps")
        if eps is not None:
            data_points += 1
            metrics["eps"] = round(eps, 2)
            if eps > 5:
                scores["earnings"] = 90
                strengths.append(f"Strong EPS of ${eps:.2f}")
            elif eps > 2:
                scores["earnings"] = 75
            elif eps > 0:
                scores["earnings"] = 55
            else:
                scores["earnings"] = 20
                weaknesses.append(f"Negative EPS of ${eps:.2f}")

        # ── Profit Margins (10%) ─────────────────────────
        profit_margin = info.get("profit_margin")
        if profit_margin is not None:
            profit_margin = _ensure_decimal_percentage(profit_margin)
            if profit_margin is not None:
                data_points += 1
                pm = _percentage_to_display(profit_margin, "margin")
                metrics["profit_margin"] = round(pm, 1)
                if pm > 20:
                    scores["margins"] = 90
                    strengths.append(f"Excellent profit margin of {pm:.1f}%")
                elif pm > 10:
                    scores["margins"] = 75
                elif pm > 5:
                    scores["margins"] = 55
                elif pm > 0:
                    scores["margins"] = 35
                    weaknesses.append(f"Thin profit margin of {pm:.1f}%")
                else:
                    scores["margins"] = 15
                    weaknesses.append(f"Negative profit margin of {pm:.1f}%")

        # ── ROE / ROA (10%) ──────────────────────────────
        roe = info.get("roe")
        if roe is not None:
            roe = _ensure_decimal_percentage(roe)
            if roe is not None:
                data_points += 1
                roe_pct = _percentage_to_display(roe, "roe_roa")
                metrics["roe"] = round(roe_pct, 1)
                if roe_pct > 20:
                    scores["returns"] = 90
                    strengths.append(f"High return on equity of {roe_pct:.1f}%")
                elif roe_pct > 10:
                    scores["returns"] = 70
                elif roe_pct > 0:
                    scores["returns"] = 45
                else:
                    scores["returns"] = 15
                    weaknesses.append(f"Negative ROE of {roe_pct:.1f}%")

        roa = info.get("roa")
        if roa is not None:
            roa = _ensure_decimal_percentage(roa)
            if roa is not None:
                roa_pct = _percentage_to_display(roa, "roe_roa")
                metrics["roa"] = round(roa_pct, 1)

        # ── Debt (10%) ───────────────────────────────────
        d2e = info.get("debt_to_equity")
        if d2e is not None:
            d2e = _ensure_decimal_percentage(d2e)
            if d2e is not None:
                data_points += 1
                # debt_to_equity can be in 0.8 (80%) or percentage form (80)
                # Convert to percentage for display
                d2e_pct = _percentage_to_display(d2e, "debt_to_equity")
                metrics["debt_to_equity"] = round(d2e_pct, 1)
                if d2e_pct < 30:
                    scores["debt"] = 90
                    strengths.append(f"Very low debt-to-equity ratio of {d2e_pct:.0f}%")
                elif d2e_pct < 80:
                    scores["debt"] = 75
                elif d2e_pct < 150:
                    scores["debt"] = 50
                elif d2e_pct < 300:
                    scores["debt"] = 30
                    weaknesses.append(f"High debt-to-equity ratio of {d2e_pct:.0f}%")
                else:
                    scores["debt"] = 10
                    weaknesses.append(f"Very high debt-to-equity ratio of {d2e_pct:.0f}%")

        # ── Free Cash Flow (10%) ─────────────────────────
        fcf = info.get("free_cash_flow")
        if fcf is not None:
            data_points += 1
            metrics["free_cash_flow"] = fcf
            if fcf > 0:
                scores["fcf"] = 80
                if fcf > 1_000_000_000:
                    strengths.append(f"Strong free cash flow of ${fcf/1e9:.1f}B")
            else:
                scores["fcf"] = 20
                weaknesses.append("Negative free cash flow")

        # ── Valuation (15%) ──────────────────────────────
        pe = info.get("pe_ratio")
        if pe is not None and pe > 0:
            data_points += 1
            metrics["pe_ratio"] = round(pe, 1)
            if pe < 15:
                scores["valuation"] = 85
                strengths.append(f"Attractive P/E ratio of {pe:.1f}x")
            elif pe < 25:
                scores["valuation"] = 70
            elif pe < 40:
                scores["valuation"] = 45
                weaknesses.append(f"Elevated P/E ratio of {pe:.1f}x")
            else:
                scores["valuation"] = 20
                weaknesses.append(f"Very high P/E ratio of {pe:.1f}x")

        forward_pe = info.get("forward_pe")
        if forward_pe is not None and forward_pe > 0:
            metrics["forward_pe"] = round(forward_pe, 1)

        peg = info.get("peg_ratio")
        if peg is not None and peg > 0:
            metrics["peg_ratio"] = round(peg, 2)
            if peg < 1:
                strengths.append(f"PEG ratio of {peg:.2f} suggests undervaluation relative to growth")
            elif peg > 3:
                weaknesses.append(f"PEG ratio of {peg:.2f} suggests overvaluation relative to growth")

        # ── Dividend (5%) ────────────────────────────────
        div_yield = info.get("dividend_yield")
        if div_yield is not None:
            div_yield = _ensure_decimal_percentage(div_yield)
            if div_yield is not None:
                data_points += 1
                dy_pct = _percentage_to_display(div_yield, "dividend")
                metrics["dividend_yield"] = round(dy_pct, 2)
                if dy_pct > 3:
                    scores["dividend"] = 85
                    strengths.append(f"Attractive dividend yield of {dy_pct:.2f}%")
                elif dy_pct > 1:
                    scores["dividend"] = 65
                elif dy_pct > 0:
                    scores["dividend"] = 50
                else:
                    scores["dividend"] = 40  # Not bad, just no dividend

        # ── Market Cap (10%) ─────────────────────────────
        market_cap = info.get("market_cap")
        if market_cap is not None:
            data_points += 1
            metrics["market_cap"] = market_cap
            if market_cap > 200_000_000_000:  # >$200B Mega cap
                scores["size"] = 90
                strengths.append("Mega-cap company with strong market presence")
            elif market_cap > 10_000_000_000:  # >$10B Large cap
                scores["size"] = 80
            elif market_cap > 2_000_000_000:  # >$2B Mid cap
                scores["size"] = 60
            elif market_cap > 300_000_000:  # >$300M Small cap
                scores["size"] = 35
                weaknesses.append("Small-cap company with higher risk")
            else:
                scores["size"] = 10
                weaknesses.append("Micro-cap company — high speculative risk")

        # ── Additional metrics ───────────────────────────
        for key in ["price_to_book", "price_to_sales", "ev_to_ebitda",
                     "operating_margin", "gross_margin", "revenue", "earnings",
                     "total_cash", "total_debt", "beta"]:
            val = info.get(key)
            if val is not None:
                if key in ("operating_margin", "gross_margin"):
                    val = _ensure_decimal_percentage(val)
                    if val is not None:
                        val = _percentage_to_display(val, "margin")
                        val = round(val, 1)
                metrics[key] = val

        # ── Calculate overall score ──────────────────────
        if data_points < 3:
            name = info.get("name") or info.get("symbol") or "This company"
            return {
                "score": 50,
                "grade": "Insufficient Data",
                "strengths": strengths,
                "weaknesses": weaknesses,
                "explanation": f"Too few fundamental metrics are available for {name} to score reliably. "
                               "The score is shown as a neutral 50 (unknown), not an assessment of quality.",
                "metrics": metrics,
            }

        weights = {
            "revenue_growth": 15, "earnings": 15, "margins": 10,
            "returns": 10, "debt": 10, "fcf": 10,
            "valuation": 15, "dividend": 5, "size": 10,
        }

        total_weight = sum(weights[k] for k in scores)
        if total_weight > 0:
            overall = sum(scores[k] * weights[k] for k in scores) / total_weight
        else:
            overall = 0

        # Grade
        if overall >= 80:
            grade = "Strong"
        elif overall >= 60:
            grade = "Healthy"
        elif overall >= 40:
            grade = "Mixed"
        elif overall >= 20:
            grade = "Weak"
        else:
            grade = "Insufficient Data"

        # Explanation
        explanation = self._generate_explanation(grade, overall, strengths, weaknesses, metrics, info)

        return {
            "score": round(overall, 1),
            "grade": grade,
            "strengths": strengths[:6],
            "weaknesses": weaknesses[:6],
            "explanation": explanation,
            "metrics": metrics,
        }

    def _generate_explanation(
        self, grade: str, score: float,
        strengths: List[str], weaknesses: List[str],
        metrics: Dict, info: Dict
    ) -> str:
        """Generate human-readable fundamental analysis summary."""
        name = info.get("name", info.get("symbol", "This company"))
        parts = [f"{name} receives a {grade} fundamental rating with a score of {score:.0f}/100."]

        if strengths:
            parts.append(f"Key strengths include: {'; '.join(strengths[:3])}.")

        if weaknesses:
            parts.append(f"Areas of concern: {'; '.join(weaknesses[:3])}.")

        mcap = metrics.get("market_cap")
        if mcap:
            if mcap > 1e12:
                parts.append(f"With a market cap of ${mcap/1e12:.1f}T, this is a well-established company.")
            elif mcap > 1e9:
                parts.append(f"With a market cap of ${mcap/1e9:.1f}B, this is a {'large' if mcap > 10e9 else 'mid'}-cap company.")

        return " ".join(parts)
