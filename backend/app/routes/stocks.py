"""
Stock & Analytics API routes.
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List

from app.database import get_db
from app.services.stock_service import StockService
from app.services.analysis_service import AnalysisService
from app.services.backtest_service import BacktestService
from app.services.ticker_service import get_ticker_service
from app.schemas.common import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stocks", tags=["Stocks"])
analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/search", response_model=APIResponse)
async def search_stocks(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    """Search stocks by symbol or company name. Uses local directory first — zero Yahoo calls for known tickers."""
    from app.utils.stock_directory import known_symbols, lookup_company_name

    ticker_service = get_ticker_service()
    canonical = ticker_service.normalize(q)

    # Local-first search: match against stock directory (no provider calls)
    query_upper = q.strip().upper()
    query_lower = q.strip().lower()
    local_results = []

    for sym in known_symbols():
        name = lookup_company_name(sym) or ""
        # Match by ticker prefix or company name substring
        if (sym.startswith(query_upper) or
            query_upper in sym or
            query_lower in name.lower()):
            local_results.append({
                "symbol": sym,
                "name": name,
                "exchange": "",
                "type": "EQUITY",
                "source": "local_directory",
            })

    # Also check portfolio holdings in DB
    from app.models.holding import Holding
    from app.models.portfolio import Portfolio
    portfolio = db.query(Portfolio).first()
    if portfolio:
        holdings = db.query(Holding).filter(
            Holding.portfolio_id == portfolio.id
        ).all()
        for h in holdings:
            if (h.symbol and (h.symbol.startswith(query_upper) or query_upper in h.symbol) and
                    not any(r["symbol"] == h.symbol for r in local_results)):
                local_results.append({
                    "symbol": h.symbol,
                    "name": h.name or lookup_company_name(h.symbol) or "",
                    "exchange": "",
                    "type": h.asset_type or "EQUITY",
                    "source": "portfolio",
                })

    # If local results found, return them without calling Yahoo
    if local_results:
        return APIResponse(data=local_results[:10])

    # Fallback to Yahoo only for unknown tickers
    service = StockService(db)
    results = await service.search_stocks(canonical)

    # Filter out invalid results (empty name, no market data = junk ticker from Yahoo)
    filtered = [
        r for r in results
        if r.get("name") and (
            r.get("sector") or r.get("market_cap") or
            r.get("type") in ("EQUITY", "ETF") or
            r.get("exchange")
        )
    ]
    return APIResponse(data=filtered[:10])


# ── Named routes BEFORE the {symbol} catch-all ──────────
@router.get("/trading-opportunities", response_model=APIResponse)
@analytics_router.get("/trading-opportunities", response_model=APIResponse)
async def get_trading_opportunities(
    refresh: bool = False,
    universe: str = "portfolio",
    selected_symbols: str = "",
    db: Session = Depends(get_db),
):
    """Get short-term swing trade setups for the specified universe.

    Args:
        universe: "portfolio" | "watchlist" | "portfolio_watchlist" | "selected"
        selected_symbols: comma-separated tickers when universe="selected"
    """
    parsed_symbols = None
    if universe == "selected" and selected_symbols:
        parsed_symbols = [s.strip().upper() for s in selected_symbols.split(",") if s.strip()]
    service = AnalysisService(db)
    result = await service.get_trading_opportunities(
        force=refresh, universe=universe, selected_symbols=parsed_symbols,
    )
    return APIResponse(data=result)


@router.get("/trading-diagnostics", response_model=APIResponse)
@analytics_router.get("/trading-diagnostics", response_model=APIResponse)
async def get_trading_diagnostics(db: Session = Depends(get_db)):
    """Comprehensive diagnostic endpoint for Trading page troubleshooting.
    
    Exposes: scan state, cache state, circuit breaker, provider health, governor.
    No API keys or secrets are exposed.
    """
    from app.utils.resilience import get_circuit_breaker, get_provider_health
    from app.utils.governor import get_governor
    from app.services.portfolio_service import PortfolioService
    from app.services.stock_service import StockService
    from app.services.analysis_service import _get_cached_result, _inflight_scans

    breaker = get_circuit_breaker("yahoo")
    health = get_provider_health()
    governor = get_governor()
    ps = PortfolioService(db)
    ss = StockService(db)

    holdings = ps.get_holdings()
    symbols = [h["symbol"] for h in holdings]

    # Cache state for each symbol
    cache_state = {}
    total_hist_rows = 0
    total_hist_cached = 0
    for sym in symbols:
        cached_hist = ss.cache.get_cached_historical(sym, "1y")
        cached_price = ss.cache.get_cached_price_any_age(sym)
        has_hist = cached_hist is not None and len(cached_hist) > 0
        has_price = cached_price is not None and cached_price.get("price") is not None
        rows = len(cached_hist) if cached_hist else 0
        total_hist_rows += rows
        if has_hist:
            total_hist_cached += 1
        cache_state[sym] = {
            "has_hist": has_hist,
            "hist_rows": rows,
            "has_price": has_price,
        }

    # Last scan result (check portfolio cache key for backwards compat)
    last_scan = _get_cached_result("trading_opportunities:portfolio") or _get_cached_result("trading_opportunities")

    return APIResponse(data={
        "circuit_breaker": breaker.snapshot(),
        "provider_health": health.snapshot(),
        "governor_stats": governor.get_stats(),
        "holdings_count": len(holdings),
        "symbols": symbols,
        "cache_summary": {
            "total_holdings": len(symbols),
            "with_hist_cache": total_hist_cached,
            "total_hist_rows": total_hist_rows,
        },
        "cache_state": cache_state,
        "last_scan": {
            "data_status": last_scan.get("data_status") if last_scan else None,
            "data_source": last_scan.get("data_source") if last_scan else None,
            "scan_duration_seconds": last_scan.get("data_quality", {}).get("scan_duration_seconds") if last_scan else None,
            "holdings_with_data": last_scan.get("data_quality", {}).get("holdings_with_data") if last_scan else None,
            "eligible_holdings": last_scan.get("data_quality", {}).get("eligible_holdings") if last_scan else None,
            "failed_symbols": last_scan.get("data_quality", {}).get("failed_symbols") if last_scan else None,
            "opportunities_found": last_scan.get("data_quality", {}).get("opportunities_found") if last_scan else None,
        },
        "inflight_scans": len(_inflight_scans),
    })


@router.get("/long-term-opportunities", response_model=APIResponse)
@analytics_router.get("/long-term-opportunities", response_model=APIResponse)
async def get_long_term_opportunities(refresh: bool = False, db: Session = Depends(get_db)):
    """Get long-term investment opportunities based on fundamental quality (cached 15 min)."""
    service = AnalysisService(db)
    result = await service.get_long_term_opportunities(force=refresh)
    return APIResponse(data=result)


@router.get("/swap-recommendations", response_model=APIResponse)
@analytics_router.get("/swap-recommendations", response_model=APIResponse)
async def get_swap_recommendations(refresh: bool = False, db: Session = Depends(get_db)):
    """Get portfolio stock-swap recommendations — identify weak holdings and suggest replacements."""
    service = AnalysisService(db)
    # Reuse trading scan result if cached (swap_recommendations are included)
    trading = await service.get_trading_opportunities(force=refresh, universe="portfolio")
    swaps = trading.get("swap_recommendations", [])
    return APIResponse(data={
        "recommendations": swaps,
        "count": len(swaps),
        "data_status": trading.get("data_status", "success"),
    })


@router.get("/portfolio-health", response_model=APIResponse)
@analytics_router.get("/portfolio-health", response_model=APIResponse)
async def get_portfolio_health(refresh: bool = False, db: Session = Depends(get_db)):
    """Generate portfolio health report (cached 15 min; ?refresh=true recomputes)."""
    service = AnalysisService(db)
    report = await service.get_portfolio_health_report(force=refresh)
    return APIResponse(data=report)


@router.get("/warmup", response_model=APIResponse)
async def warmup_portfolio(db: Session = Depends(get_db)):
    """
    Pre-warm cache for portfolio holdings. Returns immediately.
    Actual warming happens in background task.
    """
    from app.models.holding import Holding
    from app.models.portfolio import Portfolio
    from app.utils.resilience import get_circuit_breaker

    breaker = get_circuit_breaker("yahoo")
    if not breaker.allow_request():
        return APIResponse(data={
            "status": "degraded",
            "message": "Provider temporarily unavailable.",
            "warmed": 0,
            "total": 0,
        })

    portfolio = db.query(Portfolio).first()
    if not portfolio:
        return APIResponse(data={"status": "ok", "message": "No portfolio", "warmed": 0, "total": 0})

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    symbols = [h.symbol for h in holdings if h.symbol]
    if not symbols:
        return APIResponse(data={"status": "ok", "message": "No holdings", "warmed": 0, "total": 0})

    # Check if we already have cached data — skip warmup if so
    from app.services.stock_service import StockService
    stock_service = StockService(db)
    cached_count = 0
    for sym in symbols[:5]:
        cached = stock_service.cache.get_cached_historical(sym, "1y")
        if cached is not None and len(cached) > 0:
            cached_count += 1

    if cached_count >= 3:
        return APIResponse(data={
            "status": "ok",
            "message": "Cache already warm",
            "warmed": cached_count,
            "total": len(symbols),
        })

    # Launch background warmup — don't block the response
    asyncio.create_task(_do_warmup(symbols, db))

    return APIResponse(data={
        "status": "ok",
        "message": "Warmup started in background",
        "warmed": 0,
        "total": len(symbols),
    })


async def _do_warmup(symbols, db):
    """Background warmup task — runs after response is sent."""
    try:
        from app.services.stock_service import StockService
        stock_service = StockService(db)
        sem = asyncio.Semaphore(3)

        async def _warm(sym):
            async with sem:
                try:
                    await stock_service.get_stock_info(sym)
                except Exception:
                    pass

        await asyncio.gather(*[_warm(s) for s in symbols[:10]])
    except Exception as e:
        logger.warning(f"Background warmup failed: {e}")


# ── Catch-all {symbol} routes AFTER named routes ─────────
@router.get("/{symbol}", response_model=APIResponse)
async def get_stock_overview(symbol: str, db: Session = Depends(get_db)):
    """Get basic stock overview and key metrics."""
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service = StockService(db)
    overview = await service.get_stock_overview(canonical)

    # Only 404 for genuinely invalid tickers — NOT for provider timeouts
    price = overview.get("price") or {}
    price_status = price.get("status")
    error_category = price.get("error_category", "")

    # "not_found" = genuinely invalid ticker → 404
    # "unavailable"/"timeout"/"network" = provider issue → return partial data
    if price_status == "not_found" and error_category == "not_found":
        raise HTTPException(status_code=404, detail=f"Stock not found: {canonical}")

    return APIResponse(data=overview)


@router.get("/{symbol}/analysis", response_model=APIResponse)
async def get_stock_full_analysis(symbol: str, db: Session = Depends(get_db)):
    """Get full 360-degree stock analysis (fundamentals, technicals, risk, recommendations)."""
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service = AnalysisService(db)
    analysis = await service.get_full_stock_analysis(canonical)

    # Only return 404 for genuinely invalid tickers — NOT for provider timeouts
    overview = analysis.get("overview", {})
    price_data = overview.get("price", {})
    data_status = price_data.get("data_status", "success")
    error_category = price_data.get("error_category", "")

    # "not_found" = genuinely invalid ticker → 404
    # "unavailable" = provider timeout/network → return partial data with warning
    if data_status == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"No market data available for {canonical}. The ticker may be invalid or delisted."
        )

    return APIResponse(data=analysis)


@router.get("/{symbol}/history", response_model=APIResponse)
async def get_stock_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    db: Session = Depends(get_db)
):
    """Get historical OHLCV data for charts. Always ascending, deduplicated."""
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service = StockService(db)
    history = await service.get_historical_prices(canonical, period=period, interval=interval)
    # Safety net: ensure ascending order + dedup even if cache has stale-format data
    if history:
        seen = set()
        clean = []
        for row in history:
            date_key = row.get("date", "")[:10]
            if date_key in seen:
                continue
            seen.add(date_key)
            clean.append(row)
        clean.sort(key=lambda r: r.get("date", ""))
        history = clean
    return APIResponse(data=history)


@router.get("/{symbol}/news", response_model=APIResponse)
async def get_stock_news(symbol: str, limit: int = 15, db: Session = Depends(get_db)):
    """Get stock-specific news with sentiment."""
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service = StockService(db)
    news = await service.get_stock_news(canonical, limit=limit)
    return APIResponse(data=news)


@analytics_router.post("/backtest", response_model=APIResponse)
async def run_backtest(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Run strategy backtest on a stock."""
    raw_symbol = payload.get("symbol", "AAPL")
    ticker_service = get_ticker_service()
    try:
        canonical = ticker_service.validate_or_raise(raw_symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {e}")
    
    strategy = payload.get("strategy", "sma_crossover")
    period = payload.get("period", "2y")
    capital = payload.get("initial_capital", 10000.0)

    stock_service = StockService(db)
    hist = await stock_service.get_historical_prices(canonical, period=period)
    
    if not hist or len(hist) < 50:
        raise HTTPException(status_code=400, detail=f"Insufficient historical data for {canonical}. Need at least 50 data points, got {len(hist) if hist else 0}.")
    
    backtester = BacktestService()
    result = backtester.run_backtest(hist, strategy=strategy, initial_capital=capital, params=payload.get("params", {}))
    result["symbol"] = canonical
    return APIResponse(data=result)
