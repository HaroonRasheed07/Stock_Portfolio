"""Analysis-specific schemas."""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class WatchlistItemCreate(BaseModel):
    symbol: str
    notes: Optional[str] = None
    target_price: Optional[float] = None

class WatchlistItemResponse(BaseModel):
    id: int
    symbol: str
    name: Optional[str] = None
    added_at: datetime
    notes: Optional[str] = None
    target_price: Optional[float] = None
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    trend: Optional[str] = None
    fundamental_score: Optional[float] = None
    sentiment: Optional[str] = None
    risk_score: Optional[float] = None
    recommendation: Optional[str] = None

    class Config:
        from_attributes = True


class AlertCreate(BaseModel):
    symbol: Optional[str] = None
    alert_type: str
    condition: str
    threshold: Optional[float] = None
    message: Optional[str] = None
    cooldown_minutes: int = 60

class AlertResponse(BaseModel):
    id: int
    symbol: Optional[str] = None
    alert_type: str
    condition: str
    threshold: Optional[float] = None
    message: Optional[str] = None
    is_active: bool = True
    is_triggered: bool = False
    triggered_at: Optional[datetime] = None
    trigger_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True

class AlertHistoryResponse(BaseModel):
    id: int
    alert_id: int
    symbol: Optional[str] = None
    alert_type: str
    message: str
    triggered_at: datetime
    is_read: bool = False

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    risk_profile: Optional[str] = None
    investment_style: Optional[str] = None
    alerts_enabled: Optional[bool] = None
    alert_preferences: Optional[Dict[str, bool]] = None
    auto_refresh: Optional[bool] = None
    refresh_interval_minutes: Optional[int] = None
    theme: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None

class SettingsResponse(BaseModel):
    id: int
    risk_profile: str
    investment_style: str
    alerts_enabled: bool = True
    alert_preferences: Optional[Dict[str, bool]] = None
    auto_refresh: bool = True
    refresh_interval_minutes: int = 30
    theme: str = "dark"
    preferences: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class StockSearchResult(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    asset_type: Optional[str] = None
    exchange: Optional[str] = None
