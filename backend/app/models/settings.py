"""User settings model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.database import Base


class UserSettings(Base):
    """Application settings for the local user."""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Risk profile: conservative, moderate, aggressive
    risk_profile = Column(String(20), default="moderate", nullable=False)
    # Investment style: long_term, balanced, active
    investment_style = Column(String(20), default="long_term", nullable=False)
    # Alert preferences
    alerts_enabled = Column(Integer, default=1)  # SQLite boolean
    alert_preferences = Column(JSON, nullable=True, default=lambda: {
        "price_movement": True,
        "volatility_spike": True,
        "trend_change": True,
        "news_event": True,
        "negative_sentiment": True,
        "positive_catalyst": True,
        "risk_increase": True,
        "concentration": True,
        "drawdown": True,
        "fundamental_change": True,
        "earnings_upcoming": True,
    })
    # Data refresh preferences
    auto_refresh = Column(Integer, default=1)
    refresh_interval_minutes = Column(Integer, default=30)
    # Market preferences
    market_hours_only = Column(Integer, default=0)
    # Theme
    theme = Column(String(20), default="dark")
    # Misc preferences
    preferences = Column(JSON, nullable=True, default=lambda: {
        "default_chart_period": "1y",
        "holdings_sort_by": "value",
        "holdings_sort_order": "desc",
        "penny_stock_threshold": 5.0,
        "min_market_cap": 1_000_000_000,  # $1B
        "show_extended_hours": False,
    })
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
