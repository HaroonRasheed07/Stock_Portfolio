"""Portfolio snapshot model for historical tracking."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON, Index
from sqlalchemy.orm import relationship
from app.database import Base


class PortfolioSnapshot(Base):
    """Point-in-time snapshot of a portfolio for historical comparison."""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    source_file = Column(String(500), nullable=True)
    total_value = Column(Float, default=0.0)
    total_cost_basis = Column(Float, nullable=True)
    total_gain_loss = Column(Float, nullable=True)
    total_gain_loss_pct = Column(Float, nullable=True)
    num_holdings = Column(Integer, default=0)
    holdings_data = Column(JSON, nullable=True)  # Full holdings snapshot as JSON
    notes = Column(Text, nullable=True)

    # Relationships
    portfolio = relationship("Portfolio", back_populates="snapshots")

    __table_args__ = (
        Index("ix_snapshots_portfolio_date", "portfolio_id", "snapshot_date"),
    )
