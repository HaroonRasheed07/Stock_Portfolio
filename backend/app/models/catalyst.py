"""Catalyst event and alert models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Index, Boolean
from app.database import Base


class CatalystEvent(Base):
    """Normalized catalyst event from news and data sources."""
    __tablename__ = "catalyst_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    company = Column(String(500), nullable=True)
    headline = Column(String(1000), nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(200), nullable=True)
    url = Column(String(2000), nullable=True)
    published_at = Column(DateTime, nullable=True)
    retrieved_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Classification
    catalyst_type = Column(String(100), nullable=False)  # clinical_trial, fda_approval, earnings, etc.
    category = Column(String(100), nullable=True)  # broader category
    impact_level = Column(String(20), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL

    # Sentiment
    sentiment_score = Column(Float, nullable=True)  # -1.0 to 1.0
    sentiment_label = Column(String(20), nullable=True)  # positive, neutral, negative

    # Relevance & context
    relevance_score = Column(Float, nullable=True)  # 0.0 to 1.0
    confidence = Column(Float, nullable=True)  # 0.0 to 1.0
    potential_impact = Column(Text, nullable=True)  # human-readable impact description

    # Portfolio/watchlist context
    affects_holding = Column(Integer, default=0)  # SQLite boolean
    affects_watchlist = Column(Integer, default=0)  # SQLite boolean
    allocation_pct = Column(Float, nullable=True)  # portfolio allocation if held

    # Market reaction (filled after event)
    price_reaction_pct = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)  # volume / avg_volume

    # Interpretation
    long_term_view = Column(Text, nullable=True)
    short_term_view = Column(Text, nullable=True)

    # Dedup
    content_hash = Column(String(64), nullable=True, index=True)  # for dedup

    # Metadata
    provider = Column(String(50), nullable=True)  # which news provider
    raw_data = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_catalyst_symbol_date", "symbol", "published_at"),
        Index("ix_catalyst_impact", "impact_level", "published_at"),
        Index("ix_catalyst_type", "catalyst_type", "published_at"),
    )


class CatalystAlert(Base):
    """Alert generated from a catalyst event."""
    __tablename__ = "catalyst_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    catalyst_event_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)
    # Types: high_impact_catalyst, critical_news, positive_catalyst, negative_catalyst,
    #        price_reaction, volume_spike, portfolio_holding_news, watchlist_news
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=True)
    impact_level = Column(String(20), nullable=False)

    # Context
    price_reaction_pct = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)
    portfolio_exposure_pct = Column(Float, nullable=True)
    catalyst_type = Column(String(100), nullable=True)
    sentiment_label = Column(String(20), nullable=True)

    # State
    is_read = Column(Integer, default=0)
    is_dismissed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_catalyst_alert_unread", "is_read", "created_at"),
    )


class CatalystWatchItem(Base):
    """Tracks stocks receiving increasing news attention (early signals)."""
    __tablename__ = "catalyst_watch"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    company = Column(String(500), nullable=True)

    # Attention metrics
    news_frequency_24h = Column(Integer, default=0)
    news_frequency_7d = Column(Integer, default=0)
    avg_sentiment_24h = Column(Float, nullable=True)
    avg_sentiment_7d = Column(Float, nullable=True)
    high_impact_count_7d = Column(Integer, default=0)

    # Signals
    attention_trend = Column(String(20), nullable=True)  # increasing, stable, decreasing
    early_signal = Column(String(200), nullable=True)  # human-readable signal description
    early_catalyst_watch = Column(Integer, default=0)  # 1 = flagged for early catalyst monitoring

    # Context
    is_holding = Column(Integer, default=0)
    is_watchlist = Column(Integer, default=0)

    last_checked = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class NewsDedup(Base):
    """Tracks seen articles for deduplication."""
    __tablename__ = "news_dedup"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    symbol = Column(String(20), nullable=True)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String(200), nullable=True)
