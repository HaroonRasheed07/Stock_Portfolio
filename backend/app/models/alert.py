"""Alert model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from app.database import Base


class Alert(Base):
    """User-configured alert rule."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=True, index=True)  # None for portfolio-level alerts
    alert_type = Column(String(50), nullable=False)
    # Types: price_above, price_below, pct_change, volatility_spike,
    #        trend_change, negative_news, earnings_upcoming, risk_increase,
    #        concentration, drawdown, fundamental_change
    condition = Column(String(50), nullable=False)  # above, below, equals, crosses
    threshold = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    is_active = Column(Integer, default=1)  # SQLite boolean
    is_triggered = Column(Integer, default=0)
    triggered_at = Column(DateTime, nullable=True)
    trigger_count = Column(Integer, default=0)
    cooldown_minutes = Column(Integer, default=60)  # Min time between re-triggers
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_alerts_active", "is_active", "alert_type"),
    )


class AlertHistory(Base):
    """Record of triggered alerts."""
    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(20), nullable=True)
    alert_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(Text, nullable=True)  # JSON string with details
    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_read = Column(Integer, default=0)
