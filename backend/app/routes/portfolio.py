"""
Portfolio API routes.
"""
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List

from app.database import get_db
from app.services.portfolio_service import PortfolioService
from app.services.stock_service import StockService
from app.engines.risk import RiskEngine
from app.engines.rebalancing import RebalancingEngine
from app.schemas.portfolio import (
    PortfolioSummary, PortfolioDetail, CSVImportPreview, CSVImportConfirm
)
from app.schemas.common import APIResponse
from app.models.settings import UserSettings

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


def _invalidate_analysis_caches():
    """Clear cached heavy-analysis results when portfolio data changes."""
    try:
        from app.services.analysis_service import _result_cache
        _result_cache.clear()
    except Exception:
        pass


@router.get("", response_model=APIResponse)
def get_portfolio_summary(db: Session = Depends(get_db)):
    """Get portfolio summary metrics."""
    service = PortfolioService(db)
    summary = service.get_portfolio_summary()
    return APIResponse(data=summary)


@router.get("/holdings", response_model=APIResponse)
def get_holdings(
    sort_by: str = "current_value",
    sort_order: str = "desc",
    db: Session = Depends(get_db)
):
    """Get all portfolio holdings."""
    service = PortfolioService(db)
    holdings = service.get_holdings(sort_by=sort_by, sort_order=sort_order)
    return APIResponse(data=holdings)


@router.get("/performance", response_model=APIResponse)
def get_performance(db: Session = Depends(get_db)):
    """Get portfolio performance and top/worst performers."""
    service = PortfolioService(db)
    perf = service.get_performance_data()
    return APIResponse(data=perf)


@router.post("/import/preview", response_model=APIResponse)
async def preview_csv_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload CSV and preview parsed columns and row data."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV export.")

    content = await file.read()
    service = PortfolioService(db)
    preview = await service.import_csv(content, file.filename)
    return APIResponse(data=preview)


@router.post("/import/confirm", response_model=APIResponse)
async def confirm_csv_import(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Confirm CSV import and store holdings."""
    service = PortfolioService(db)
    result = await service.confirm_import(payload)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Import failed"))
    _invalidate_analysis_caches()
    return APIResponse(data=result, message="Portfolio imported successfully.")


@router.post("/refresh", response_model=APIResponse)
async def refresh_portfolio_data(db: Session = Depends(get_db)):
    """Refresh current market prices and info for all holdings.
    Returns immediately — sector population runs in background."""
    import asyncio
    service = PortfolioService(db)

    async def _bg_refresh():
        try:
            await service.refresh_holdings_data()
            _invalidate_analysis_caches()
        except Exception as e:
            logger.warning(f"Background refresh failed: {e}")

    asyncio.create_task(_bg_refresh())
    return APIResponse(data={"status": "refreshing"}, message="Refresh started. Prices will update shortly.")


@router.get("/snapshots", response_model=APIResponse)
def get_snapshots(db: Session = Depends(get_db)):
    """Get portfolio history snapshots."""
    service = PortfolioService(db)
    snapshots = service.get_snapshots()
    return APIResponse(data=snapshots)


@router.get("/risk-summary", response_model=APIResponse)
async def get_risk_summary(db: Session = Depends(get_db)):
    """Get comprehensive risk summary for dashboard using the full risk engine."""
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_event_loop()

    service = PortfolioService(db)
    holdings = service.get_holdings()

    if not holdings:
        return APIResponse(data={"risk_score": 0, "risk_level": "Unknown", "penny_stocks": 0, "total_holdings": 0})

    # Basic metrics
    penny_stocks = sum(1 for h in holdings if h.get("current_price") is not None and h["current_price"] < 5.0)
    priced_holdings = [h for h in holdings if h.get("current_price") is not None and h["current_price"] > 0]
    total_value = sum(h.get("current_value", 0) or 0 for h in holdings)
    large_positions = sum(1 for h in holdings if total_value > 0 and ((h.get("current_value", 0) or 0) / total_value) > 0.15)
    avg_price = sum(h["current_price"] for h in priced_holdings) / len(priced_holdings) if priced_holdings else 0

    # Fetch historical data in ONE batched download (was N serial calls)
    stock_service = StockService(db)
    symbols = [h["symbol"] for h in holdings]
    hist_rows = await stock_service.get_batch_historical_prices(symbols, period="1y")

    historical_data = {}
    for sym, rows in hist_rows.items():
        if not rows:
            continue
        df = pd.DataFrame(rows)
        if not df.empty and "date" in df.columns:
            df.rename(columns={"close": "Close", "open": "Open", "high": "High", "low": "Low", "volume": "Volume"}, inplace=True)
            historical_data[sym] = df

    # Run risk engine OFF the event loop to avoid blocking
    risk_engine = RiskEngine()
    portfolio_risk = await loop.run_in_executor(
        None, lambda: risk_engine.analyze_portfolio(holdings, historical_data)
    )

    # Get risk profile and adjust thresholds
    settings = db.query(UserSettings).first()
    risk_profile = settings.risk_profile if settings else "moderate"
    profile_multipliers = {"conservative": 0.8, "moderate": 1.0, "aggressive": 1.3}
    multiplier = profile_multipliers.get(risk_profile, 1.0)
    adjusted_score = min(100, portfolio_risk.get("risk_score", 0) * multiplier)

    # Recalculate risk level based on profile-adjusted score
    if adjusted_score <= 20:
        risk_level = "Low"
    elif adjusted_score <= 40:
        risk_level = "Moderate"
    elif adjusted_score <= 60:
        risk_level = "Elevated"
    else:
        risk_level = "High"

    # Build warnings
    warnings = []
    if penny_stocks > 0:
        warnings.append(f"{penny_stocks} penny stock(s) detected (< $5)")
    if large_positions > 0:
        warnings.append(f"{large_positions} oversized position(s) (> 15%)")
    vol = portfolio_risk.get("portfolio_volatility")
    if vol and vol > 0.30:
        warnings.append(f"High portfolio volatility: {vol*100:.1f}%")
    beta = portfolio_risk.get("portfolio_beta")
    if beta and beta > 1.2:
        warnings.append(f"Above-market beta: {beta}")
    corr = portfolio_risk.get("correlation_risk")
    if corr and corr > 60:
        warnings.append(f"High correlation between holdings: {corr:.0f}%")
    sector = portfolio_risk.get("sector_concentration")
    if sector and sector > 40:
        warnings.append(f"Sector concentration risk: {sector:.0f}%")

    return APIResponse(data={
        "risk_score": round(adjusted_score, 1),
        "risk_level": risk_level,
        "risk_profile": risk_profile,
        "penny_stocks": penny_stocks,
        "large_positions": large_positions,
        "total_holdings": len(holdings),
        "avg_price": round(avg_price, 2),
        "portfolio_volatility": portfolio_risk.get("portfolio_volatility"),
        "portfolio_beta": portfolio_risk.get("portfolio_beta"),
        "concentration_risk": portfolio_risk.get("concentration_risk"),
        "sector_concentration": portfolio_risk.get("sector_concentration"),
        "correlation_risk": portfolio_risk.get("correlation_risk"),
        "contributors": portfolio_risk.get("contributors", []),
        "explanation": portfolio_risk.get("explanation", ""),
        "warnings": warnings,
    })


@router.get("/rebalancing", response_model=APIResponse)
async def get_rebalancing_analysis(db: Session = Depends(get_db)):
    """Analyse current allocation vs targets and suggest rebalancing moves."""
    service = PortfolioService(db)
    holdings = service.get_holdings()
    if not holdings:
        return APIResponse(data={"summary": "No holdings to analyse.", "suggestions": []})
    engine = RebalancingEngine()
    result = engine.analyze(holdings)
    return APIResponse(data=result)
