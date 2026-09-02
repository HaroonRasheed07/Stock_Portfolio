"""
Watchlist, Alerts, and Settings API routes.
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from datetime import datetime

from app.database import get_db
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert, AlertHistory
from app.models.settings import UserSettings
from app.schemas.common import APIResponse
from app.services.stock_service import StockService
from app.services.ticker_service import get_ticker_service

router = APIRouter(tags=["User Features"])

# High-quality large-cap candidates for watchlist auto-fill
# These are established, well-known companies across sectors
_WATCHLIST_SUGGESTIONS = [
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "reason": "AI/semiconductor leader"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "reason": "Search/cloud/AI giant"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "reason": "E-commerce/cloud leader"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "reason": "Social media/AI"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "reason": "EV/clean energy leader"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway", "reason": "Diversified conglomerate"},
    {"symbol": "LLY", "name": "Eli Lilly", "reason": "Pharma/GLP-1 leader"},
    {"symbol": "AVGO", "name": "Broadcom Inc.", "reason": "Semiconductor/AI infrastructure"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "reason": "Healthcare conglomerate"},
    {"symbol": "V", "name": "Visa Inc.", "reason": "Payment network duopoly"},
]


# ── Watchlist ────────────────────────────────────────────

@router.get("/watchlist", response_model=APIResponse)
async def get_watchlist(db: Session = Depends(get_db)):
    """Get watchlist items enriched with price and trend.
    Auto-populates with high-quality candidates when watchlist is empty.
    Fetches missing prices for watchlist-only symbols."""
    items = db.query(WatchlistItem).order_by(WatchlistItem.added_at.desc()).all()

    # Auto-populate when watchlist is truly empty (no user items at all)
    if not items:
        await _auto_populate_watchlist(db)
        items = db.query(WatchlistItem).order_by(WatchlistItem.added_at.desc()).all()

    stock_service = StockService(db)
    result = []

    # Collect symbols missing from price cache and fetch them in batch
    missing_symbols = []
    for item in items:
        price_data = stock_service.cache.get_cached_price_any_age(item.symbol)
        if not price_data or not price_data.get("price"):
            missing_symbols.append(item.symbol)

    if missing_symbols:
        try:
            from app.utils.resilience import get_circuit_breaker
            breaker = get_circuit_breaker("yahoo")
            if breaker.allow_request():
                # Bounded timeout: don't let batch price fetch hang the entire watchlist
                try:
                    prices = await asyncio.wait_for(
                        stock_service.provider.get_batch_prices(missing_symbols),
                        timeout=60,
                    )
                    for sym, pdata in prices.items():
                        if pdata and pdata.get("price"):
                            stock_service.cache.set_cached_price(sym, pdata)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Batch price fetch for watchlist timed out after 15s "
                        f"({len(missing_symbols)} symbols)"
                    )
        except Exception as e:
            logger.warning(f"Batch price fetch for watchlist failed: {e}")

    for item in items:
        # Use cached price (any age) for display — fetch above fills gaps
        price_data = stock_service.cache.get_cached_price_any_age(item.symbol) or {}
        # Info from cache only (no live fetch for speed)
        info = stock_service.cache.get_cached_stock_info(item.symbol) or {}
        result.append({
            "id": item.id,
            "symbol": item.symbol,
            "name": item.name or info.get("name"),
            "added_at": item.added_at,
            "notes": item.notes,
            "target_price": item.target_price,
            "current_price": price_data.get("price"),
            "change_pct": price_data.get("change_pct"),
            "sector": info.get("sector"),
            "market_cap": info.get("market_cap"),
        })

    return APIResponse(data=result)


async def _auto_populate_watchlist(db: Session):
    """Populate empty watchlist with high-quality large-cap stocks.
    Excludes portfolio holdings. Does NOT overwrite existing items."""
    from app.models.holding import Holding
    from app.models.portfolio import Portfolio

    portfolio_symbols = set()
    try:
        portfolio = db.query(Portfolio).first()
        if portfolio:
            holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
            portfolio_symbols = {h.symbol for h in holdings if h.symbol}
    except Exception:
        pass

    existing_symbols = {item.symbol for item in db.query(WatchlistItem).all()}
    excluded = portfolio_symbols | existing_symbols

    added = 0
    for candidate in _WATCHLIST_SUGGESTIONS:
        if added >= 8:
            break
        sym = candidate["symbol"]
        if sym in excluded:
            continue
        item = WatchlistItem(
            symbol=sym,
            name=candidate["name"],
            notes=candidate.get("reason", ""),
        )
        db.add(item)
        added += 1

    if added > 0:
        db.commit()


@router.post("/watchlist", response_model=APIResponse)
async def add_to_watchlist(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Add a stock to watchlist."""
    ticker_service = get_ticker_service()
    raw_symbol = payload.get("symbol", "")
    if not raw_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    
    try:
        symbol = ticker_service.validate_or_raise(raw_symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = db.query(WatchlistItem).filter(WatchlistItem.symbol == symbol).first()
    if existing:
        return APIResponse(data={"symbol": symbol}, message="Symbol already on watchlist")

    stock_service = StockService(db)
    info = await stock_service.get_stock_info(symbol)

    item = WatchlistItem(
        symbol=symbol,
        name=info.get("name"),
        notes=payload.get("notes"),
        target_price=payload.get("target_price"),
    )
    db.add(item)
    db.commit()
    return APIResponse(data={"symbol": symbol}, message=f"Added {symbol} to watchlist.")


@router.delete("/watchlist/{symbol}", response_model=APIResponse)
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db)):
    """Remove symbol from watchlist."""
    db.query(WatchlistItem).filter(WatchlistItem.symbol == symbol.upper()).delete()
    db.commit()
    return APIResponse(message=f"Removed {symbol.upper()} from watchlist.")


@router.get("/watchlist/suggestions", response_model=APIResponse)
def get_watchlist_suggestions(db: Session = Depends(get_db)):
    """Get suggested stocks for watchlist auto-fill.
    Excludes symbols already in portfolio or watchlist."""
    portfolio_symbols = set()
    watchlist_symbols = set()

    try:
        from app.models.holding import Holding
        from app.models.portfolio import Portfolio
        portfolio = db.query(Portfolio).first()
        if portfolio:
            holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
            portfolio_symbols = {h.symbol for h in holdings if h.symbol}
    except Exception:
        pass

    try:
        items = db.query(WatchlistItem).all()
        watchlist_symbols = {item.symbol for item in items}
    except Exception:
        pass

    excluded = portfolio_symbols | watchlist_symbols
    suggestions = [
        s for s in _WATCHLIST_SUGGESTIONS
        if s["symbol"] not in excluded
    ]

    return APIResponse(data=suggestions)


# ── Alerts ───────────────────────────────────────────────

@router.get("/alerts", response_model=APIResponse)
def get_alerts(db: Session = Depends(get_db)):
    """Get all configured alerts and alert history."""
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).all()
    history = db.query(AlertHistory).order_by(AlertHistory.triggered_at.desc()).limit(20).all()

    return APIResponse(data={
        "rules": [
            {
                "id": a.id, "symbol": a.symbol, "alert_type": a.alert_type,
                "condition": a.condition, "threshold": a.threshold,
                "message": a.message, "is_active": bool(a.is_active),
                "is_triggered": bool(a.is_triggered), "triggered_at": a.triggered_at,
            } for a in alerts
        ],
        "history": [
            {
                "id": h.id, "alert_id": h.alert_id, "symbol": h.symbol,
                "alert_type": h.alert_type, "message": h.message,
                "triggered_at": h.triggered_at, "is_read": bool(h.is_read),
            } for h in history
        ],
    })


@router.post("/alerts", response_model=APIResponse)
def create_alert(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Create a new alert rule."""
    ticker_service = get_ticker_service()
    raw_symbol = payload.get("symbol", "")
    symbol = None
    if raw_symbol:
        try:
            symbol = ticker_service.validate_or_raise(raw_symbol)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    alert = Alert(
        symbol=symbol,
        alert_type=payload.get("alert_type", "price_above"),
        condition=payload.get("condition", "above"),
        threshold=payload.get("threshold"),
        message=payload.get("message"),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return APIResponse(data={"id": alert.id}, message="Alert created successfully.")


@router.delete("/alerts/{alert_id}", response_model=APIResponse)
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """Delete an alert rule."""
    db.query(Alert).filter(Alert.id == alert_id).delete()
    db.commit()
    return APIResponse(message="Alert deleted.")


# ── Settings ─────────────────────────────────────────────

@router.get("/settings", response_model=APIResponse)
def get_settings_route(db: Session = Depends(get_db)):
    """Get application settings."""
    settings = db.query(UserSettings).first()
    if not settings:
        settings = UserSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return APIResponse(data={
        "id": settings.id,
        "risk_profile": settings.risk_profile,
        "investment_style": settings.investment_style,
        "alerts_enabled": bool(settings.alerts_enabled),
        "alert_preferences": settings.alert_preferences,
        "auto_refresh": bool(settings.auto_refresh),
        "refresh_interval_minutes": settings.refresh_interval_minutes,
        "theme": settings.theme,
        "preferences": settings.preferences,
    })


@router.put("/settings", response_model=APIResponse)
def update_settings(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Update settings."""
    settings = db.query(UserSettings).first()
    if not settings:
        settings = UserSettings()
        db.add(settings)

    if "risk_profile" in payload:
        settings.risk_profile = payload["risk_profile"]
    if "investment_style" in payload:
        settings.investment_style = payload["investment_style"]
    if "alerts_enabled" in payload:
        settings.alerts_enabled = 1 if payload["alerts_enabled"] else 0
    if "alert_preferences" in payload:
        settings.alert_preferences = payload["alert_preferences"]
    if "theme" in payload:
        settings.theme = payload["theme"]

    settings.updated_at = datetime.utcnow()
    db.commit()
    return APIResponse(message="Settings updated successfully.")
