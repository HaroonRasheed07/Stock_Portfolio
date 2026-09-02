"""
Abstract data provider interfaces.
All data sources must implement these interfaces, enabling provider swapping
without changing business logic.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd


class MarketDataProvider(ABC):
    """Interface for market price data."""

    @abstractmethod
    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """Get current price and basic quote data.
        Returns: {price, previous_close, open, high, low, volume, change, change_pct, ...}
        """
        pass

    @abstractmethod
    async def get_historical_prices(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> pd.DataFrame:
        """Get historical OHLCV data.
        Args:
            symbol: Stock ticker
            period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max
            interval: 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo
        Returns: DataFrame with columns [Open, High, Low, Close, Volume]
        """
        pass

    @abstractmethod
    async def get_batch_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get current prices for multiple symbols at once."""
        pass

    @abstractmethod
    async def search_symbol(self, query: str) -> List[Dict[str, Any]]:
        """Search for a stock symbol.
        Returns: [{symbol, name, exchange, type}, ...]
        """
        pass


class FundamentalDataProvider(ABC):
    """Interface for fundamental/financial data."""

    @abstractmethod
    async def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive stock information.
        Returns: {name, sector, industry, market_cap, description, employees, ...}
        """
        pass

    @abstractmethod
    async def get_financials(self, symbol: str) -> Dict[str, Any]:
        """Get financial statements data.
        Returns: {income_statement, balance_sheet, cash_flow}
        """
        pass

    @abstractmethod
    async def get_key_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get key financial metrics.
        Returns: {pe_ratio, eps, revenue, profit_margin, roe, debt_to_equity, ...}
        """
        pass

    @abstractmethod
    async def get_earnings(self, symbol: str) -> Dict[str, Any]:
        """Get earnings history and upcoming earnings date.
        Returns: {earnings_history, next_earnings_date, ...}
        """
        pass


class NewsProvider(ABC):
    """Interface for news data."""

    @abstractmethod
    async def get_stock_news(
        self, symbol: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get news articles for a specific stock.
        Returns: [{title, summary, source, url, published_at, ...}, ...]
        """
        pass

    @abstractmethod
    async def get_market_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get general market news.
        Returns: [{title, summary, source, url, published_at, ...}, ...]
        """
        pass


class SentimentProvider(ABC):
    """Interface for sentiment analysis."""

    @abstractmethod
    async def analyze_text_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of a text string.
        Returns: {score: float (-1 to 1), label: str (positive/neutral/negative)}
        """
        pass

    @abstractmethod
    async def get_stock_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get aggregated sentiment for a stock based on recent news.
        Returns: {overall_score, label, positive_count, neutral_count, negative_count}
        """
        pass
