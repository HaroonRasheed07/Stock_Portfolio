"""Common Pydantic schemas."""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool = True
    data: Any = None
    message: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = datetime.utcnow()


class PaginatedResponse(BaseModel):
    """Paginated response."""
    items: list = []
    total: int = 0
    page: int = 1
    per_page: int = 50
    has_more: bool = False


class CacheInfo(BaseModel):
    """Cache metadata."""
    cached_at: Optional[datetime] = None
    ttl_seconds: Optional[int] = None
    is_stale: bool = False
    source: str = "cache"
