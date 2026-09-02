"""
Technical analysis engine using the `ta` library.
Computes indicators, trend classification, and signals.
"""
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
import ta

logger = logging.getLogger(__name__)


class TechnicalEngine:
    """Computes technical indicators and trend analysis."""

    def analyze(self, df: pd.DataFrame, current_price: float = 0) -> Dict[str, Any]:
        """
        Run full technical analysis on OHLCV DataFrame.
        DataFrame must have columns: Date, Open, High, Low, Close, Volume
        """
        if df.empty or len(df) < 20:
            return {
                "indicators": {},
                "trend": "Insufficient Data",
                "trend_strength": 0,
                "momentum": "Neutral",
                "signals": [],
                "support_levels": [],
                "resistance_levels": [],
                "explanation": "Insufficient historical data for technical analysis.",
            }

        try:
            close = df["Close"].astype(float)
            high = df["High"].astype(float)
            low = df["Low"].astype(float)
            volume = df["Volume"].astype(float)

            if current_price == 0:
                current_price = float(close.iloc[-1])

            indicators = {}
            signals = []

            # ── Moving Averages ──────────────────────────
            if len(close) >= 20:
                indicators["sma_20"] = round(float(ta.trend.sma_indicator(close, window=20).iloc[-1]), 2)
            if len(close) >= 50:
                indicators["sma_50"] = round(float(ta.trend.sma_indicator(close, window=50).iloc[-1]), 2)
            if len(close) >= 200:
                indicators["sma_200"] = round(float(ta.trend.sma_indicator(close, window=200).iloc[-1]), 2)

            indicators["ema_12"] = round(float(ta.trend.ema_indicator(close, window=12).iloc[-1]), 2)
            indicators["ema_26"] = round(float(ta.trend.ema_indicator(close, window=26).iloc[-1]), 2)

            # MA Signals
            if indicators.get("sma_50") and indicators.get("sma_200"):
                if indicators["sma_50"] > indicators["sma_200"]:
                    signals.append({"signal": "Golden Cross Active", "type": "bullish", "description": "50-day SMA is above 200-day SMA"})
                else:
                    signals.append({"signal": "Death Cross Active", "type": "bearish", "description": "50-day SMA is below 200-day SMA"})

            if indicators.get("sma_200"):
                if current_price > indicators["sma_200"]:
                    signals.append({"signal": "Above 200-day SMA", "type": "bullish", "description": "Price is trading above its long-term moving average"})
                else:
                    signals.append({"signal": "Below 200-day SMA", "type": "bearish", "description": "Price is trading below its long-term moving average"})

            # ── RSI ──────────────────────────────────────
            rsi = ta.momentum.rsi(close, window=14)
            indicators["rsi_14"] = round(float(rsi.iloc[-1]), 2)

            if indicators["rsi_14"] > 70:
                signals.append({"signal": "RSI Overbought", "type": "bearish", "description": f"RSI at {indicators['rsi_14']:.0f}, indicating overbought conditions"})
            elif indicators["rsi_14"] < 30:
                signals.append({"signal": "RSI Oversold", "type": "bullish", "description": f"RSI at {indicators['rsi_14']:.0f}, indicating oversold conditions"})

            # ── MACD ─────────────────────────────────────
            macd_line = ta.trend.macd(close)
            macd_signal = ta.trend.macd_signal(close)
            macd_hist = ta.trend.macd_diff(close)

            indicators["macd"] = round(float(macd_line.iloc[-1]), 4)
            indicators["macd_signal"] = round(float(macd_signal.iloc[-1]), 4)
            indicators["macd_histogram"] = round(float(macd_hist.iloc[-1]), 4)

            if indicators["macd"] > indicators["macd_signal"]:
                signals.append({"signal": "MACD Bullish", "type": "bullish", "description": "MACD line is above signal line"})
            else:
                signals.append({"signal": "MACD Bearish", "type": "bearish", "description": "MACD line is below signal line"})

            # ── Bollinger Bands ──────────────────────────
            bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            indicators["bb_upper"] = round(float(bb.bollinger_hband().iloc[-1]), 2)
            indicators["bb_middle"] = round(float(bb.bollinger_mavg().iloc[-1]), 2)
            indicators["bb_lower"] = round(float(bb.bollinger_lband().iloc[-1]), 2)

            if current_price > indicators["bb_upper"]:
                signals.append({"signal": "Above Upper Bollinger", "type": "bearish", "description": "Price is above upper Bollinger Band"})
            elif current_price < indicators["bb_lower"]:
                signals.append({"signal": "Below Lower Bollinger", "type": "bullish", "description": "Price is below lower Bollinger Band"})

            # ── ATR & ADX ────────────────────────────────
            atr = ta.volatility.average_true_range(high, low, close, window=14)
            indicators["atr_14"] = round(float(atr.iloc[-1]), 2)

            if len(close) >= 14:
                adx = ta.trend.adx(high, low, close, window=14)
                indicators["adx_14"] = round(float(adx.iloc[-1]), 2)
                if indicators["adx_14"] > 25:
                    signals.append({"signal": "Strong Trend", "type": "neutral", "description": f"ADX at {indicators['adx_14']:.0f}, indicating a strong trend"})

            # ── Volume ───────────────────────────────────
            avg_vol_20 = volume.rolling(20).mean().iloc[-1]
            indicators["volume"] = int(volume.iloc[-1])
            indicators["avg_volume_20"] = int(avg_vol_20) if not pd.isna(avg_vol_20) else 0
            indicators["volume_ratio"] = round(float(volume.iloc[-1] / avg_vol_20), 2) if avg_vol_20 > 0 else 1.0

            if indicators["volume_ratio"] > 2.0:
                signals.append({"signal": "High Volume", "type": "neutral", "description": f"Volume is {indicators['volume_ratio']:.1f}x the 20-day average"})

            # ── Support/Resistance ───────────────────────
            support_levels, resistance_levels = self._calculate_sr_levels(df, current_price)
            indicators["support"] = support_levels[0] if support_levels else None
            indicators["resistance"] = resistance_levels[0] if resistance_levels else None

            # ── Trend Classification ─────────────────────
            trend, trend_strength = self._classify_trend(indicators, current_price, close)
            momentum = self._classify_momentum(indicators, signals)

            # ── Explanation ──────────────────────────────
            explanation = self._generate_explanation(trend, trend_strength, momentum, signals, indicators, current_price)

            return {
                "indicators": indicators,
                "trend": trend,
                "trend_strength": round(trend_strength, 1),
                "momentum": momentum,
                "signals": signals,
                "support_levels": support_levels[:3],
                "resistance_levels": resistance_levels[:3],
                "explanation": explanation,
            }

        except Exception as e:
            logger.error(f"Technical analysis error: {e}")
            return {
                "indicators": {},
                "trend": "Error",
                "trend_strength": 0,
                "momentum": "Neutral",
                "signals": [],
                "support_levels": [],
                "resistance_levels": [],
                "explanation": f"Technical analysis could not be completed: {str(e)}",
            }

    def _calculate_sr_levels(self, df: pd.DataFrame, current_price: float) -> tuple:
        """Calculate support and resistance levels using pivot points and recent highs/lows."""
        support = []
        resistance = []

        try:
            recent = df.tail(60)
            highs = recent["High"].astype(float)
            lows = recent["Low"].astype(float)

            # Pivot point levels
            pivot = (highs.iloc[-1] + lows.iloc[-1] + float(recent["Close"].iloc[-1])) / 3
            r1 = 2 * pivot - lows.iloc[-1]
            s1 = 2 * pivot - highs.iloc[-1]
            r2 = pivot + (highs.iloc[-1] - lows.iloc[-1])
            s2 = pivot - (highs.iloc[-1] - lows.iloc[-1])

            # Recent swing lows as support
            for i in range(2, len(lows) - 2):
                if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
                    if lows.iloc[i] < current_price:
                        support.append(round(float(lows.iloc[i]), 2))

            # Recent swing highs as resistance
            for i in range(2, len(highs) - 2):
                if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
                    if highs.iloc[i] > current_price:
                        resistance.append(round(float(highs.iloc[i]), 2))

            # Add pivot levels
            if s1 < current_price:
                support.append(round(float(s1), 2))
            if s2 < current_price:
                support.append(round(float(s2), 2))
            if r1 > current_price:
                resistance.append(round(float(r1), 2))
            if r2 > current_price:
                resistance.append(round(float(r2), 2))

            # Sort: support descending (closest first), resistance ascending
            support = sorted(set(support), reverse=True)
            resistance = sorted(set(resistance))

        except Exception as e:
            logger.warning(f"S/R calculation error: {e}")

        return support, resistance

    def _classify_trend(self, indicators: Dict, current_price: float, close: pd.Series) -> tuple:
        """Classify trend strength and direction."""
        score = 50  # neutral starting point

        # Price vs MAs
        if indicators.get("sma_20") and current_price > indicators["sma_20"]:
            score += 5
        elif indicators.get("sma_20"):
            score -= 5

        if indicators.get("sma_50") and current_price > indicators["sma_50"]:
            score += 10
        elif indicators.get("sma_50"):
            score -= 10

        if indicators.get("sma_200") and current_price > indicators["sma_200"]:
            score += 15
        elif indicators.get("sma_200"):
            score -= 15

        # MA alignment
        if (indicators.get("sma_20") and indicators.get("sma_50") and
            indicators["sma_20"] > indicators["sma_50"]):
            score += 5
        elif indicators.get("sma_20") and indicators.get("sma_50"):
            score -= 5

        # MACD
        if indicators.get("macd", 0) > indicators.get("macd_signal", 0):
            score += 5
        else:
            score -= 5

        # ADX (trend strength, not direction)
        adx = indicators.get("adx_14", 20)
        strength_multiplier = min(adx / 40, 1.5)

        # Clamp
        score = max(0, min(100, score))

        if score >= 75:
            trend = "Strong Uptrend"
        elif score >= 60:
            trend = "Uptrend"
        elif score >= 40:
            trend = "Neutral"
        elif score >= 25:
            trend = "Downtrend"
        else:
            trend = "Strong Downtrend"

        return trend, score

    def _classify_momentum(self, indicators: Dict, signals: List) -> str:
        """Classify momentum based on oscillators."""
        bullish = sum(1 for s in signals if s["type"] == "bullish")
        bearish = sum(1 for s in signals if s["type"] == "bearish")
        diff = bullish - bearish

        if diff >= 3:
            return "Strong Bullish"
        elif diff >= 1:
            return "Bullish"
        elif diff <= -3:
            return "Strong Bearish"
        elif diff <= -1:
            return "Bearish"
        return "Neutral"

    def _generate_explanation(
        self, trend: str, strength: float, momentum: str,
        signals: List, indicators: Dict, price: float
    ) -> str:
        """Generate human-readable technical analysis summary."""
        parts = [f"The stock is in a {trend.lower()} with a trend strength of {strength:.0f}/100."]
        parts.append(f"Current momentum is {momentum.lower()}.")

        # Key levels
        if indicators.get("sma_200"):
            rel = "above" if price > indicators["sma_200"] else "below"
            pct = abs((price - indicators["sma_200"]) / indicators["sma_200"] * 100)
            parts.append(f"Price is {pct:.1f}% {rel} the 200-day moving average (${indicators['sma_200']:.2f}).")

        # RSI
        rsi = indicators.get("rsi_14")
        if rsi:
            if rsi > 70:
                parts.append(f"RSI at {rsi:.0f} suggests overbought conditions.")
            elif rsi < 30:
                parts.append(f"RSI at {rsi:.0f} suggests oversold conditions.")
            else:
                parts.append(f"RSI at {rsi:.0f} is in neutral territory.")

        # Key signals
        key_signals = [s["description"] for s in signals[:3]]
        if key_signals:
            parts.append("Key signals: " + "; ".join(key_signals) + ".")

        return " ".join(parts)
