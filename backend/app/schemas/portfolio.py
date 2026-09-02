"""Portfolio and holding Pydantic schemas."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ── Holding schemas ──────────────────────────────────────

class HoldingBase(BaseModel):
    symbol: str
    name: Optional[str] = None
    quantity: float = 0.0
    avg_price: Optional[float] = None
    cost_basis: Optional[float] = None

class HoldingCreate(HoldingBase):
    current_value: Optional[float] = None
    unrealized_gain: Optional[float] = None
    unrealized_gain_pct: Optional[float] = None

class HoldingResponse(HoldingBase):
    id: int
    portfolio_id: int
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    unrealized_gain: Optional[float] = None
    unrealized_gain_pct: Optional[float] = None
    allocation_pct: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    asset_type: str = "stock"
    # Enriched fields (populated by analysis)
    day_change: Optional[float] = None
    day_change_pct: Optional[float] = None
    risk_score: Optional[float] = None
    trend: Optional[str] = None
    fundamental_score: Optional[float] = None
    sentiment: Optional[str] = None
    recommendation: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Portfolio schemas ────────────────────────────────────

class PortfolioSummary(BaseModel):
    id: int
    name: str
    total_value: float = 0.0
    total_cost_basis: float = 0.0
    total_gain_loss: float = 0.0
    total_gain_loss_pct: float = 0.0
    day_change: float = 0.0
    day_change_pct: float = 0.0
    num_holdings: int = 0
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    diversification_score: Optional[float] = None
    health_score: Optional[float] = None
    last_updated: Optional[datetime] = None

    class Config:
        from_attributes = True


class PortfolioDetail(PortfolioSummary):
    holdings: List[HoldingResponse] = []
    sector_allocation: Dict[str, float] = {}
    top_performers: List[HoldingResponse] = []
    worst_performers: List[HoldingResponse] = []

    class Config:
        from_attributes = True


class PortfolioPerformance(BaseModel):
    total_value: float = 0.0
    total_cost_basis: float = 0.0
    total_return: float = 0.0
    total_return_pct: float = 0.0
    day_change: float = 0.0
    day_change_pct: float = 0.0
    best_performer: Optional[Dict[str, Any]] = None
    worst_performer: Optional[Dict[str, Any]] = None
    value_history: List[Dict[str, Any]] = []  # [{date, value}]


# ── CSV Import schemas ───────────────────────────────────

class CSVColumnMapping(BaseModel):
    """Maps detected CSV columns to expected fields."""
    symbol: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[str] = None
    avg_price: Optional[str] = None
    cost_basis: Optional[str] = None
    current_value: Optional[str] = None
    unrealized_gain: Optional[str] = None
    unrealized_gain_pct: Optional[str] = None

class CSVPreviewRow(BaseModel):
    symbol: str
    name: Optional[str] = None
    quantity: float = 0.0
    avg_price: Optional[float] = None
    cost_basis: Optional[float] = None
    current_value: Optional[float] = None
    unrealized_gain: Optional[float] = None
    unrealized_gain_pct: Optional[float] = None
    warnings: List[str] = []
    errors: List[str] = []

class CSVImportPreview(BaseModel):
    """Preview of parsed CSV before import confirmation."""
    filename: str
    total_rows: int = 0
    valid_rows: int = 0
    error_rows: int = 0
    detected_columns: List[str] = []
    column_mapping: CSVColumnMapping = CSVColumnMapping()
    preview_rows: List[CSVPreviewRow] = []
    warnings: List[str] = []
    errors: List[str] = []
    estimated_total_value: float = 0.0

class CSVImportConfirm(BaseModel):
    """Confirmation request for CSV import."""
    filename: str
    column_mapping: CSVColumnMapping
    snapshot_date: Optional[datetime] = None
    notes: Optional[str] = None


# ── Snapshot schemas ─────────────────────────────────────

class SnapshotResponse(BaseModel):
    id: int
    snapshot_date: datetime
    source_file: Optional[str] = None
    total_value: float = 0.0
    total_cost_basis: Optional[float] = None
    total_gain_loss: Optional[float] = None
    total_gain_loss_pct: Optional[float] = None
    num_holdings: int = 0
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class SnapshotComparison(BaseModel):
    """Comparison between two portfolio snapshots."""
    previous: SnapshotResponse
    current: SnapshotResponse
    value_change: float = 0.0
    value_change_pct: float = 0.0
    holdings_added: List[str] = []
    holdings_removed: List[str] = []
    allocation_changes: List[Dict[str, Any]] = []
