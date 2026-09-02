"""Holding model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


class Holding(Base):
    """Represents a single stock/ETF holding in a portfolio."""
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    name = Column(String(500), nullable=True)
    quantity = Column(Float, nullable=False, default=0.0)
    avg_price = Column(Float, nullable=True)  # Can be missing
    cost_basis = Column(Float, nullable=True)  # Can be missing
    current_price = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)
    unrealized_gain = Column(Float, nullable=True)
    unrealized_gain_pct = Column(Float, nullable=True)
    allocation_pct = Column(Float, nullable=True)
    sector = Column(String(100), nullable=True)
    industry = Column(String(200), nullable=True)
    asset_type = Column(String(50), default="stock")  # stock, etf, reit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    portfolio = relationship("Portfolio", back_populates="holdings")

    __table_args__ = (
        Index("ix_holdings_portfolio_symbol", "portfolio_id", "symbol", unique=True),
    )
