"""Stock data cache models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Index
from app.database import Base


class StockInfo(Base):
    """Cached stock information (sector, market cap, etc.)."""
    __tablename__ = "stock_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    name = Column(String(500), nullable=True)
    sector = Column(String(100), nullable=True)
    industry = Column(String(200), nullable=True)
    market_cap = Column(Float, nullable=True)
    asset_type = Column(String(50), nullable=True)  # stock, etf, reit
    exchange = Column(String(50), nullable=True)
    currency = Column(String(10), default="USD")
    country = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    website = Column(String(500), nullable=True)
    employees = Column(Integer, nullable=True)
    extra_data = Column(JSON, nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_stock_info_cached", "symbol", "cached_at"),
    )


class PriceCache(Base):
    """Cached current price data."""
    __tablename__ = "price_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    price = Column(Float, nullable=False)
    previous_close = Column(Float, nullable=True)
    open_price = Column(Float, nullable=True)
    day_high = Column(Float, nullable=True)
    day_low = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    avg_volume = Column(Float, nullable=True)
    fifty_two_week_high = Column(Float, nullable=True)
    fifty_two_week_low = Column(Float, nullable=True)
    change = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FundamentalCache(Base):
    """Cached fundamental data."""
    __tablename__ = "fundamental_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    data = Column(JSON, nullable=True)  # Full fundamental data as JSON
    financials = Column(JSON, nullable=True)  # Income statement data
    balance_sheet = Column(JSON, nullable=True)
    cash_flow = Column(JSON, nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class HistoricalPriceCache(Base):
    """Cached historical price data."""
    __tablename__ = "historical_price_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    period = Column(String(20), nullable=False)  # 1mo, 3mo, 6mo, 1y, 2y, 5y, max
    data = Column(JSON, nullable=True)  # OHLCV data as JSON
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_hist_price_symbol_period", "symbol", "period", unique=True),
    )


class NewsCache(Base):
    """Cached news articles."""
    __tablename__ = "news_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=True, index=True)  # None for market news
    title = Column(String(1000), nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(200), nullable=True)
    url = Column(String(2000), nullable=True)
    published_at = Column(DateTime, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(String(20), nullable=True)  # positive, neutral, negative
    impact = Column(String(20), nullable=True)  # low, medium, high
    category = Column(String(100), nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_news_symbol_date", "symbol", "published_at"),
    )


class AnalysisCache(Base):
    """Cached analysis results."""
    __tablename__ = "analysis_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    analysis_type = Column(String(50), nullable=False)
    # Types: technical, fundamental, risk, recommendation, sentiment, catalyst
    result = Column(JSON, nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_analysis_symbol_type", "symbol", "analysis_type", unique=True),
    )
