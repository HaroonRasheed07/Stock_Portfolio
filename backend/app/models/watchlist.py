"""Watchlist model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from app.database import Base


class WatchlistItem(Base):
    """A stock on the user's watchlist."""
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    name = Column(String(500), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)
    target_price = Column(Float, nullable=True)
    alert_enabled = Column(Integer, default=0)  # SQLite-compatible boolean
