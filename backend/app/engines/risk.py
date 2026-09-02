"""
Risk analysis engine.
Calculates per-stock and portfolio-level risk metrics.
"""
import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS = 252


class RiskEngine:
    """Calculates risk metrics for individual stocks and portfolios."""

    def analyze_stock(self, historical_df: pd.DataFrame, beta: Optional[float] = None) -> Dict[str, Any]:
        """Calculate risk metrics for a single stock."""
        if historical_df.empty or len(historical_df) < 30:
            return {
                "volatility": None,
                "beta": beta,
                "max_drawdown": None,
                "var_95": None,
                "downside_deviation": None,
                "sharpe_ratio": None,
                "risk_score": 50,
                "risk_level": "Unknown",
            }

        try:
            close = historical_df["Close"].astype(float)
            returns = close.pct_change().dropna()

            if len(returns) < 20:
                return {"risk_score": 50, "risk_level": "Unknown"}

            # Annualized volatility
            vol_std = returns.std()
            volatility = float(vol_std * np.sqrt(TRADING_DAYS)) if pd.notna(vol_std) and vol_std > 0 else 0.0

            # Max drawdown
            cumulative = (1 + returns).cumprod()
            rolling_max = cumulative.cummax()
            drawdowns = (cumulative - rolling_max) / rolling_max
            max_drawdown = float(drawdowns.min())

            # Value at Risk (95%)
            var_95 = float(np.percentile(returns, 5))

            # Downside deviation
            negative_returns = returns[returns < 0]
            downside_dev = float(negative_returns.std() * np.sqrt(TRADING_DAYS)) if len(negative_returns) > 0 else 0

            # Sharpe ratio (assuming risk-free rate of ~4.5%)
            risk_free_daily = 0.045 / TRADING_DAYS
            excess_returns = returns - risk_free_daily
            ret_std = returns.std()
            sharpe = float(excess_returns.mean() / ret_std * np.sqrt(TRADING_DAYS)) if pd.notna(ret_std) and ret_std > 0 else 0

            # Risk score (0-100, higher = more risky)
            risk_score = self._calculate_risk_score(volatility, max_drawdown, var_95, beta, downside_dev)

            # Risk level
            if risk_score <= 25:
                risk_level = "Low"
            elif risk_score <= 50:
                risk_level = "Moderate"
            elif risk_score <= 75:
                risk_level = "Elevated"
            else:
                risk_level = "High"

            return {
                "volatility": round(volatility, 4),
                "beta": round(beta, 2) if beta else None,
                "max_drawdown": round(max_drawdown, 4),
                "var_95": round(var_95, 4),
                "downside_deviation": round(downside_dev, 4),
                "sharpe_ratio": round(sharpe, 2),
                "risk_score": round(risk_score, 1),
                "risk_level": risk_level,
            }
        except Exception as e:
            logger.error(f"Risk analysis error: {e}")
            return {"risk_score": 50, "risk_level": "Unknown"}

    def analyze_portfolio(
        self,
        holdings_data: List[Dict[str, Any]],
        historical_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """Calculate portfolio-level risk metrics."""
        if not holdings_data:
            return {
                "risk_score": 0,
                "risk_level": "Unknown",
                "explanation": "No holdings to analyze.",
                "contributors": [],
            }

        try:
            total_value = sum(h.get("current_value", 0) or 0 for h in holdings_data)
            if total_value == 0:
                return {"risk_score": 0, "risk_level": "Unknown"}

            # ── Concentration risk (HHI) ─────────────────
            weights = []
            for h in holdings_data:
                w = (h.get("current_value", 0) or 0) / total_value if total_value > 0 else 0
                weights.append(w)

            hhi = sum(w**2 for w in weights)
            # Normalize HHI: 1/N (perfect) to 1 (single stock)
            n = len(holdings_data)
            min_hhi = 1.0 / n if n > 0 else 1
            concentration_score = (hhi - min_hhi) / (1 - min_hhi) * 100 if n > 1 else 100

            # ── Sector concentration ─────────────────────
            sector_weights = {}
            for h in holdings_data:
                sector = h.get("sector", "Unknown") or "Unknown"
                value = h.get("current_value", 0) or 0
                sector_weights[sector] = sector_weights.get(sector, 0) + value / total_value

            sector_hhi = sum(w**2 for w in sector_weights.values())
            sector_concentration = sector_hhi * 100

            # ── Portfolio volatility ─────────────────────
            symbols = [h["symbol"] for h in holdings_data if h.get("symbol")]
            returns_dict = {}
            for symbol in symbols:
                if symbol in historical_data and not historical_data[symbol].empty:
                    close = historical_data[symbol]["Close"].astype(float)
                    ret = close.pct_change().dropna()
                    if len(ret) > 20:
                        returns_dict[symbol] = ret

            portfolio_volatility = None
            portfolio_beta = None
            correlation_risk = None

            # Compute portfolio beta as weighted average of individual betas
            beta_weighted_sum = 0.0
            beta_weight_count = 0
            for h in holdings_data:
                b = h.get("beta")
                w = (h.get("current_value", 0) or 0) / total_value
                if b is not None:
                    beta_weighted_sum += b * w
                    beta_weight_count += w
            if beta_weight_count > 0:
                portfolio_beta = round(beta_weighted_sum / beta_weight_count, 2)

            if len(returns_dict) >= 2:
                # Align returns to common dates
                returns_df = pd.DataFrame(returns_dict)
                returns_df = returns_df.dropna()

                if len(returns_df) >= 20:
                    # Correlation matrix
                    corr_matrix = returns_df.corr()

                    # Average pairwise correlation
                    n_assets = len(corr_matrix)
                    if n_assets > 1:
                        upper_triangle = []
                        for i in range(n_assets):
                            for j in range(i+1, n_assets):
                                upper_triangle.append(corr_matrix.iloc[i, j])
                        avg_correlation = np.mean(upper_triangle)
                        correlation_risk = round(float(max(0, avg_correlation)) * 100, 1)

                    # Portfolio variance
                    port_weights = np.array([
                        (h.get("current_value", 0) or 0) / total_value
                        for h in holdings_data
                        if h["symbol"] in returns_dict
                    ])
                    if len(port_weights) == len(returns_df.columns):
                        cov_matrix = returns_df.cov() * TRADING_DAYS
                        port_var = float(port_weights @ cov_matrix.values @ port_weights)
                        portfolio_volatility = round(float(np.sqrt(port_var)), 4)

            # ── Portfolio risk score ─────────────────────
            scores = {
                "concentration": concentration_score * 0.20,
                "sector_concentration": sector_concentration * 0.10,
            }

            if portfolio_volatility is not None:
                vol_score = min(portfolio_volatility / 0.40 * 100, 100)  # 40% vol = 100 risk
                scores["volatility"] = vol_score * 0.25
            if correlation_risk is not None:
                scores["correlation"] = correlation_risk * 0.15

            # Individual stock risk contribution
            avg_stock_risk = 0
            contributors = []
            for h in holdings_data:
                symbol = h["symbol"]
                weight = (h.get("current_value", 0) or 0) / total_value
                if symbol in historical_data and not historical_data[symbol].empty:
                    stock_risk = self.analyze_stock(historical_data[symbol], h.get("beta"))
                    avg_stock_risk += stock_risk["risk_score"] * weight
                    if weight > 0.05:  # Only show significant positions
                        contributors.append({
                            "symbol": symbol,
                            "weight": round(weight * 100, 1),
                            "risk_score": stock_risk["risk_score"],
                            "risk_level": stock_risk["risk_level"],
                            "volatility": stock_risk.get("volatility"),
                        })

            scores["stock_risk"] = avg_stock_risk * 0.30

            total_risk = sum(scores.values())
            risk_score = min(100, max(0, total_risk))

            if risk_score <= 25:
                risk_level = "Low"
            elif risk_score <= 50:
                risk_level = "Moderate"
            elif risk_score <= 75:
                risk_level = "Elevated"
            else:
                risk_level = "High"

            # Sort contributors by risk
            contributors.sort(key=lambda x: x["risk_score"], reverse=True)

            explanation = self._generate_explanation(
                risk_score, risk_level, concentration_score,
                sector_concentration, portfolio_volatility,
                correlation_risk, contributors, holdings_data,
            )

            return {
                "risk_score": round(risk_score, 1),
                "risk_level": risk_level,
                "portfolio_volatility": portfolio_volatility,
                "portfolio_beta": portfolio_beta,
                "concentration_risk": round(concentration_score, 1),
                "sector_concentration": round(sector_concentration, 1),
                "correlation_risk": correlation_risk,
                "contributors": contributors[:10],
                "explanation": explanation,
            }

        except Exception as e:
            logger.error(f"Portfolio risk analysis error: {e}")
            return {"risk_score": 50, "risk_level": "Unknown", "explanation": str(e)}

    def _calculate_risk_score(
        self, volatility: float, max_drawdown: float,
        var_95: float, beta: Optional[float], downside_dev: float
    ) -> float:
        """Calculate composite risk score for a single stock."""
        score = 0

        # Volatility component (25%)
        vol_pct = volatility * 100
        if vol_pct < 15:
            score += 5
        elif vol_pct < 25:
            score += 12.5
        elif vol_pct < 40:
            score += 18.75
        else:
            score += 25

        # Max drawdown component (25%)
        dd_pct = abs(max_drawdown) * 100
        if dd_pct < 10:
            score += 5
        elif dd_pct < 20:
            score += 12.5
        elif dd_pct < 35:
            score += 18.75
        else:
            score += 25

        # VaR component (20%)
        var_pct = abs(var_95) * 100
        if var_pct < 1.5:
            score += 4
        elif var_pct < 2.5:
            score += 10
        elif var_pct < 4:
            score += 15
        else:
            score += 20

        # Beta component (15%)
        if beta is not None:
            if beta < 0.8:
                score += 3
            elif beta < 1.2:
                score += 7.5
            elif beta < 1.5:
                score += 11.25
            else:
                score += 15

        # Downside deviation (15%)
        dd_ann = downside_dev * 100
        if dd_ann < 10:
            score += 3
        elif dd_ann < 18:
            score += 7.5
        elif dd_ann < 30:
            score += 11.25
        else:
            score += 15

        return min(100, max(0, score))

    def _generate_explanation(
        self, risk_score: float, risk_level: str,
        concentration: float, sector_conc: float,
        volatility: Optional[float], correlation: Optional[float],
        contributors: List[Dict], holdings: List[Dict],
    ) -> str:
        """Generate human-readable risk analysis summary."""
        parts = [f"Portfolio risk score is {risk_score:.0f}/100 ({risk_level})."]

        if concentration > 50:
            top_holdings = sorted(holdings, key=lambda x: x.get("current_value", 0) or 0, reverse=True)[:3]
            names = [h.get("symbol", "") for h in top_holdings]
            parts.append(f"Position concentration is high — top holdings ({', '.join(names)}) dominate the portfolio.")
        elif concentration > 30:
            parts.append("Moderate position concentration.")

        if sector_conc > 40:
            parts.append("Sector concentration is elevated — consider diversifying across sectors.")

        if volatility:
            parts.append(f"Portfolio volatility is {volatility*100:.1f}% annualized.")

        if correlation and correlation > 60:
            parts.append(f"Average correlation between holdings is {correlation:.0f}%, which reduces diversification benefits.")

        if contributors:
            top_risk = contributors[0]
            parts.append(f"Highest risk contributor: {top_risk['symbol']} (risk score: {top_risk['risk_score']:.0f}, weight: {top_risk['weight']:.1f}%).")

        return " ".join(parts)
