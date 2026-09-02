"""
Backtesting service.
Runs historical backtests for defined technical strategies.
"""
import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class BacktestService:
    """Executes backtests on historical stock data."""

    def run_backtest(
        self,
        historical_data: List[Dict[str, Any]],
        strategy: str = "sma_crossover",
        initial_capital: float = 10000.0,
        params: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Run backtest strategy on historical OHLCV list."""
        if not historical_data or len(historical_data) < 50:
            return {
                "symbol": "N/A",
                "strategy": strategy,
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "num_trades": 0,
                "profit_loss": 0.0,
                "trades": [],
                "equity_curve": [],
                "assumptions": ["Insufficient data points for backtesting (minimum 50 bars required)"],
            }

        df = pd.DataFrame(historical_data)
        df["close"] = df["close"].astype(float)
        params = params or {}

        capital = initial_capital
        position = 0
        entry_price = 0
        trades = []
        equity_curve = []

        # ── Strategy Signal Generation ───────────────────
        if strategy == "sma_crossover":
            fast = params.get("fast_period", 20)
            slow = params.get("slow_period", 50)
            df["fast_ma"] = df["close"].rolling(fast).mean()
            df["slow_ma"] = df["close"].rolling(slow).mean()
            df["signal"] = 0
            df.loc[df["fast_ma"] > df["slow_ma"], "signal"] = 1  # Buy signal

        elif strategy == "rsi_reversal":
            rsi_period = params.get("rsi_period", 14)
            # Basic RSI formula
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(rsi_period).mean()
            rs = gain / loss
            df["rsi"] = 100 - (100 / (1 + rs))
            df["signal"] = 0
            df.loc[df["rsi"] < 30, "signal"] = 1  # Oversold Buy
            df.loc[df["rsi"] > 70, "signal"] = -1  # Overbought Sell
        else:
            # Default Buy & Hold
            df["signal"] = 1

        # Simulation Loop
        for i in range(len(df)):
            date = df.iloc[i]["date"]
            price = df.iloc[i]["close"]
            sig = df.iloc[i]["signal"]

            # Signal execution
            if sig == 1 and position == 0:
                # Buy
                position = capital / price
                entry_price = price
                trades.append({
                    "type": "BUY", "date": date, "price": price,
                    "shares": round(position, 4), "capital": round(capital, 2)
                })
            elif sig == -1 and position > 0:
                # Sell
                capital = position * price
                pnl = (price - entry_price) * position
                trades.append({
                    "type": "SELL", "date": date, "price": price,
                    "shares": round(position, 4), "capital": round(capital, 2),
                    "pnl": round(pnl, 2), "pnl_pct": round((price/entry_price - 1)*100, 2)
                })
                position = 0

            current_val = position * price if position > 0 else capital
            equity_curve.append({"date": date, "equity": round(current_val, 2)})

        # Close final open position
        if position > 0:
            final_price = df.iloc[-1]["close"]
            capital = position * final_price
            pnl = (final_price - entry_price) * position
            trades.append({
                "type": "SELL (END)", "date": df.iloc[-1]["date"], "price": final_price,
                "shares": round(position, 4), "capital": round(capital, 2),
                "pnl": round(pnl, 2), "pnl_pct": round((final_price/entry_price - 1)*100, 2)
            })

        # Calculate performance stats
        total_return_pct = round((capital - initial_capital) / initial_capital * 100, 2)
        profit_loss = round(capital - initial_capital, 2)

        sell_trades = [t for t in trades if "SELL" in t["type"]]
        winning_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        win_rate = round(len(winning_trades) / len(sell_trades) * 100, 1) if sell_trades else 0.0

        # Max drawdown
        eq_series = pd.Series([e["equity"] for e in equity_curve])
        cummax = eq_series.cummax()
        drawdown = (eq_series - cummax) / cummax
        max_dd = round(abs(float(drawdown.min())) * 100, 2) if not drawdown.empty else 0.0

        return {
            "strategy": strategy,
            "total_return": total_return_pct,
            "annualized_return": round(total_return_pct / (len(df) / 252), 2) if len(df) > 0 else 0,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "num_trades": len(sell_trades),
            "profit_loss": profit_loss,
            "trades": trades,
            "equity_curve": equity_curve[::max(1, len(equity_curve)//100)],  # Downsample for UI
            "assumptions": [
                "No transaction costs or slippage modeled.",
                "Executions assume instant fill at bar close price.",
                "No look-ahead bias enforced.",
            ],
        }
