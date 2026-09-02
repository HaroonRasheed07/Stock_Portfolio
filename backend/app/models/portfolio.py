"""Portfolio model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Portfolio(Base):
    """Represents a user's portfolio."""
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), default="My Portfolio", nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    total_value = Column(Float, default=0.0)
    total_cost_basis = Column(Float, default=0.0)
    total_gain_loss = Column(Float, default=0.0)
    total_gain_loss_pct = Column(Float, default=0.0)

    # Relationships
    holdings = relationship("Holding", back_populates="portfolio", cascade="all, delete-orphan")
    snapshots = relationship("PortfolioSnapshot", back_populates="portfolio", cascade="all, delete-orphan")
