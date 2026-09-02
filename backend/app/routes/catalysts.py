"""
Catalyst & News Alert Engine API routes.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.services.catalyst_service import CatalystService
from app.services.ticker_service import get_ticker_service
from app.schemas.common import APIResponse

router = APIRouter(prefix="/catalysts", tags=["Catalysts"])


@router.get("/summary", response_model=APIResponse)
async def get_catalyst_summary(db: Session = Depends(get_db)):
    """Get overall catalyst summary (dashboard widget)."""
    service = CatalystService(db)
    summary = service.get_catalyst_summary()
    return APIResponse(data=summary)


@router.get("/events", response_model=APIResponse)
async def get_catalyst_events(
    symbol: Optional[str] = Query(None),
    impact_level: Optional[str] = Query(None),
    catalyst_type: Optional[str] = Query(None),
    scope: Optional[str] = Query(None, pattern="^(all|portfolio|watchlist)$"),
    limit: int = Query(50, ge=1, le=200),
    hours_back: int = Query(72, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """Get catalyst events with optional filters. scope: all|portfolio|watchlist."""
    service = CatalystService(db)
    events = service.get_catalyst_events(
        symbol=symbol,
        impact_level=impact_level,
        catalyst_type=catalyst_type,
        scope=scope,
        limit=limit,
        hours_back=hours_back,
    )
    return APIResponse(data=events)


@router.get("/timeline/{symbol}", response_model=APIResponse)
async def get_catalyst_timeline(
    symbol: str,
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get catalyst timeline for a specific stock."""
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service = CatalystService(db)
    timeline = service.get_catalyst_timeline(canonical, limit=limit)
    return APIResponse(data=timeline)


@router.get("/alerts", response_model=APIResponse)
async def get_catalyst_alerts(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get catalyst alerts."""
    service = CatalystService(db)
    alerts = service.get_catalyst_alerts(unread_only=unread_only, limit=limit)
    count = service.get_unread_alert_count()
    return APIResponse(data={"alerts": alerts, "unread_count": count})


@router.post("/alerts/{alert_id}/read", response_model=APIResponse)
async def mark_alert_read(alert_id: int, db: Session = Depends(get_db)):
    """Mark a catalyst alert as read."""
    service = CatalystService(db)
    service.mark_alert_read(alert_id)
    return APIResponse(message="Alert marked as read.")


@router.post("/alerts/read-all", response_model=APIResponse)
async def mark_all_alerts_read(db: Session = Depends(get_db)):
    """Mark all catalyst alerts as read."""
    service = CatalystService(db)
    service.mark_all_alerts_read()
    return APIResponse(message="All alerts marked as read.")


@router.post("/alerts/{alert_id}/dismiss", response_model=APIResponse)
async def dismiss_alert(alert_id: int, db: Session = Depends(get_db)):
    """Dismiss a catalyst alert."""
    service = CatalystService(db)
    service.dismiss_alert(alert_id)
    return APIResponse(message="Alert dismissed.")


@router.get("/watch", response_model=APIResponse)
async def get_catalyst_watch(db: Session = Depends(get_db)):
    """Get catalyst watch items (stocks with increasing attention)."""
    service = CatalystService(db)
    items = service.get_catalyst_watch()
    return APIResponse(data=items)


@router.get("/sentiment/{symbol}", response_model=APIResponse)
async def get_stock_sentiment(symbol: str, db: Session = Depends(get_db)):
    """Get combined sentiment and catalyst data for a stock."""
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service = CatalystService(db)
    data = service.get_stock_sentiment_with_catalyst(canonical)
    return APIResponse(data=data)


# ── Scan triggers (manual refresh) ────────────────────────

@router.post("/scan/{symbol}", response_model=APIResponse)
async def scan_symbol(symbol: str, db: Session = Depends(get_db)):
    """Manually trigger a catalyst scan for a symbol."""
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service = CatalystService(db)
    result = await service.scan_symbol(canonical)
    return APIResponse(data=result, message=f"Catalyst scan completed for {canonical}.")


@router.post("/scan-portfolio", response_model=APIResponse)
async def scan_portfolio(db: Session = Depends(get_db)):
    """Manually trigger catalyst scan for all portfolio holdings."""
    service = CatalystService(db)
    result = await service.scan_portfolio()
    return APIResponse(data=result, message="Portfolio catalyst scan completed.")


@router.post("/scan-watchlist", response_model=APIResponse)
async def scan_watchlist(db: Session = Depends(get_db)):
    """Manually trigger catalyst scan for all watchlist stocks."""
    service = CatalystService(db)
    result = await service.scan_watchlist()
    return APIResponse(data=result, message="Watchlist catalyst scan completed.")


@router.post("/scan-market", response_model=APIResponse)
async def scan_market_news(db: Session = Depends(get_db)):
    """Manually trigger scan of general market news for catalysts."""
    service = CatalystService(db)
    result = await service.scan_market_news()
    return APIResponse(data=result, message="Market news catalyst scan completed.")


@router.post("/reclassify", response_model=APIResponse)
async def reclassify_events(db: Session = Depends(get_db)):
    """Reclassify all existing events based on actual symbol mentions."""
    service = CatalystService(db)
    result = service.reclassify_events()
    return APIResponse(data=result, message="Events reclassified.")
