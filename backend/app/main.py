"""
FastAPI application entry point.
"""
import logging as _early_logging
_early_logging.getLogger("yfinance").setLevel(_early_logging.CRITICAL)
_early_logging.getLogger("yfinance").addHandler(_early_logging.NullHandler())
_early_logging.getLogger("urllib3").setLevel(_early_logging.ERROR)

import logging
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db, SessionLocal, get_db
from app.routes.portfolio import router as portfolio_router
from app.routes.stocks import router as stocks_router, analytics_router
from app.routes.user_features import router as user_router
from app.routes.catalysts import router as catalyst_router
from app.utils.request_tracer import get_request_tracer

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class _ConnectionResetFilter(logging.Filter):
    """Suppress harmless Windows ProactorEventLoop connection-reset noise.

    Browsers abort pre-flight/keep-alive connections routinely; asyncio logs
    a full traceback (WinError 10054) for each. These are not application
    errors, so we drop them from the log output.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[0] is ConnectionResetError:
            return False
        msg = record.getMessage()
        if "ConnectionResetError" in msg or "_call_connection_lost" in msg or "10054" in msg:
            return False
        return True


# Suppress on all noisy loggers
for _lname in ("asyncio", "uvicorn", "uvicorn.error", "uvicorn.access", "watchfiles"):
    logging.getLogger(_lname).addFilter(_ConnectionResetFilter())

# Background polling state
_background_task = None
_stop_polling = asyncio.Event()
_background_delay_seconds = 120  # Delay first scan to let dashboard load first (2 minutes)


async def _background_catalyst_polling():
    """Background task that periodically scans for catalysts.

    CRITICAL ARCHITECTURE:
    - Does NOT start until 60 seconds after server startup
    - This allows the dashboard to load and populate cache FIRST
    - Checks circuit breaker before each symbol scan
    - Adds delays between symbols to avoid 429 storms
    - Stops entirely if breaker is open
    - Skips symbols whose news is already fresh in cache
    """
    from app.services.catalyst_service import CatalystService
    from app.utils.resilience import get_circuit_breaker

    # CRITICAL: Wait before first scan so dashboard can load first
    logger.info(
        f"Background catalyst polling starting in {_background_delay_seconds}s "
        f"(waiting for dashboard warmup)..."
    )
    try:
        await asyncio.wait_for(_stop_polling.wait(), timeout=_background_delay_seconds)
        logger.info("Background catalyst polling stopped during startup delay.")
        return
    except asyncio.TimeoutError:
        pass  # Timeout = delay elapsed, proceed with scan

    logger.info("Background catalyst polling started.")
    while not _stop_polling.is_set():
        try:
            db = SessionLocal()
            try:
                service = CatalystService(db)
                breaker = get_circuit_breaker("yahoo")

                # Check if breaker is open BEFORE starting scan
                if not breaker.allow_request():
                    logger.warning(
                        "Background scan skipped: circuit breaker open. "
                        "Will retry next cycle."
                    )
                else:
                    # Scan portfolio holdings with throttling
                    portfolio_symbols = service._get_portfolio_symbols()
                    results = {}
                    scanned = 0
                    for symbol in portfolio_symbols:
                        if _stop_polling.is_set():
                            break
                        # Check breaker before each symbol
                        if not breaker.allow_request():
                            logger.warning(
                                f"Background scan stopping early: circuit breaker "
                                f"opened after {scanned}/{len(portfolio_symbols)} symbols"
                            )
                            break
                        try:
                            result = await service.scan_symbol(symbol)
                            results[symbol] = result
                            scanned += 1
                            # Throttle between symbols: 1s minimum
                            await asyncio.sleep(1.0)
                        except Exception as e:
                            logger.error(f"Error scanning {symbol}: {e}")
                            results[symbol] = {"error": str(e)}

                    new_catalysts = sum(
                        r.get("new_catalysts", 0) for r in results.values()
                        if isinstance(r, dict)
                    )
                    logger.info(
                        f"Portfolio scan complete: {scanned} symbols, "
                        f"{new_catalysts} new catalysts"
                    )

                # Small delay between portfolio and market scan
                await asyncio.sleep(5)

                # Scan general market news (single SPY call)
                if breaker.allow_request():
                    market_result = await service.scan_market_news()
                    logger.info(
                        f"Market scan complete: "
                        f"{market_result.get('actionable_catalysts', 0)} actionable catalysts"
                    )

                # Clean up old dedup entries weekly (runs every cycle, only cleans once)
                from datetime import datetime, timedelta
                now = datetime.utcnow()
                if now.hour == 3 and now.minute < 15:  # ~3 AM cleanup window
                    service._cleanup_old_dedup(days=7)

            finally:
                db.close()
        except Exception as e:
            logger.error(f"Background catalyst polling error: {e}", exc_info=True)

        # Wait for next cycle or stop signal (30 minutes default)
        try:
            await asyncio.wait_for(_stop_polling.wait(), timeout=1800)
            break  # Stop event was set
        except asyncio.TimeoutError:
            pass  # Timeout means we should poll again

    logger.info("Background catalyst polling stopped.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    global _background_task
    logger.info("Initializing database...")
    init_db()

    # Fix any stale/incorrect tickers in the database (V00 -> VOO, etc.)
    try:
        from app.services.ticker_service import get_ticker_service
        from app.models.holding import Holding
        ticker_svc = get_ticker_service()
        db = SessionLocal()
        try:
            holdings = db.query(Holding).all()
            fixed = 0
            for h in holdings:
                canonical = ticker_svc.normalize(h.symbol or "")
                if canonical and canonical != h.symbol:
                    logger.info(f"Fixing stale ticker: {h.symbol} -> {canonical}")
                    h.symbol = canonical
                    fixed += 1
            if fixed:
                db.commit()
                logger.info(f"Fixed {fixed} stale ticker(s) in portfolio")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Ticker migration on startup failed: {e}")

    # Add early_catalyst_watch column if missing
    try:
        import sqlite3
        from app.config import get_settings
        settings = get_settings()
        db_path = str(settings.DATA_DIR / "portfolio.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(catalyst_watch)")
        columns = [row[1] for row in cursor.fetchall()]
        if "early_catalyst_watch" not in columns:
            conn.execute("ALTER TABLE catalyst_watch ADD COLUMN early_catalyst_watch INTEGER DEFAULT 0")
            conn.commit()
            logger.info("Added early_catalyst_watch column to catalyst_watch")
        conn.close()
    except Exception as e:
        logger.warning(f"early_catalyst_watch migration on startup failed: {e}")

    logger.info("Application startup complete.")

    # Start background catalyst polling
    _stop_polling.clear()
    _background_task = asyncio.create_task(_background_catalyst_polling())
    logger.info("Background catalyst polling task created.")

    yield

    # Shutdown
    logger.info("Application shutdown — stopping background tasks.")
    _stop_polling.set()
    if _background_task:
        try:
            await asyncio.wait_for(_background_task, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _background_task.cancel()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="Stock Portfolio Intelligence Platform",
    description="Production-quality local portfolio intelligence and stock-analysis API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for Next.js frontend
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
# Allow LAN/private-network origins so phones/tablets on the same network can
# use the app (frontend served from http://<dev-ip>:3000). Local-only app:
# never allow arbitrary public origins.
_private_origin_regex = (
    r"https?://(localhost|127\.0\.0\.1"
    r"|192\.168(\.\d{1,3}){2}"
    r"|10(\.\d{1,3}){2}"
    r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2})"
    r"(:\d+)?"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=_private_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(portfolio_router)
app.include_router(stocks_router)
app.include_router(analytics_router)
app.include_router(user_router)
app.include_router(catalyst_router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": "Stock Portfolio Intelligence Platform", "version": "1.0.0"}


@app.get("/diagnostics")
def diagnostics(db=Depends(get_db)):
    """
    Comprehensive diagnostics endpoint: provider health, circuit breaker state,
    request tracing, cache freshness, and portfolio data quality.
    """
    from app.utils.resilience import get_provider_health, get_circuit_breaker
    from app.utils.request_tracer import get_request_tracer
    from app.models.holding import Holding
    from app.utils.cache import CacheManager
    from datetime import datetime

    provider_health = get_provider_health().snapshot()
    breaker = get_circuit_breaker("yahoo").snapshot()
    tracer_summary = get_request_tracer().summary()

    yahoo_health = provider_health.get("yahoo", {})
    by_category = yahoo_health.get("by_category", {})

    # Request rate: total requests / elapsed time since first call
    total_requests = yahoo_health.get("requests_total", 0)
    tracer_total = tracer_summary.get("total_calls", 0)
    request_rate = None
    if tracer_total > 0 and tracer_summary.get("total_calls", 0) > 0:
        calls = get_request_tracer().get_raw_calls()
        if calls:
            elapsed_s = time.time() - calls[0]["timestamp"]
            if elapsed_s > 0:
                request_rate = round(tracer_total / elapsed_s, 3)

    # Cache age from tracer (last call timestamp)
    cache_age_seconds = None
    calls_raw = get_request_tracer().get_raw_calls()
    if calls_raw:
        cache_age_seconds = round(time.time() - calls_raw[-1]["timestamp"], 1)

    holdings_count = db.query(Holding).count()
    symbols = [h.symbol for h in db.query(Holding.symbol).all()]

    # Per-holding cache/data quality
    cache_mgr = CacheManager(db)
    symbol_status = []
    fresh_prices = 0
    fresh_info = 0
    stale_data_count = 0
    for sym in sorted({s[0] if isinstance(s, tuple) else s["symbol"] if isinstance(s, dict) else s for s in symbols}):
        price = cache_mgr.get_cached_price(sym)
        info = cache_mgr.get_cached_stock_info_any_age(sym)
        has_price = bool(price and price.get("price"))
        has_name = bool(info and info.get("name"))
        fresh_prices += 1 if has_price else 0
        fresh_info += 1 if has_name else 0
        symbol_status.append({
            "symbol": sym,
            "has_price": has_price,
            "has_company_data": has_name,
        })

    # Stale data count from tracer
    stale_data_count = tracer_summary.get("stale_served", 0)

    return {
        "status": "ok",
        "providers": {
            "yahoo": {
                "requests_total": total_requests,
                "cache_hits": yahoo_health.get("cache_hits", 0),
                "successes": yahoo_health.get("successes", 0),
                "failures": yahoo_health.get("failures", 0),
                "request_rate_per_second": request_rate,
                "last_success_at": yahoo_health.get("last_success_at"),
                "last_failure_at": yahoo_health.get("last_failure_at"),
                "last_failure_message": yahoo_health.get("last_failure_message", ""),
                "avg_duration_ms": yahoo_health.get("avg_duration_ms"),
                "by_category": by_category,
                "circuit_breaker": breaker,
            },
        },
        "request_tracing": {
            "total_calls": tracer_total,
            "cache_hits": tracer_summary.get("cache_hits", 0),
            "cache_misses": tracer_summary.get("cache_misses", 0),
            "successes": tracer_summary.get("successes", 0),
            "failures": tracer_summary.get("failures", 0),
            "batch_calls": tracer_summary.get("batch_calls", 0),
            "individual_calls": tracer_summary.get("individual_calls", 0),
            "stale_served": stale_data_count,
            "rate_limits": tracer_summary.get("rate_limits", 0),
            "json_errors": by_category.get("parse_error", 0),
            "timeout_count": by_category.get("timeout", 0),
            "tickers_fetched": tracer_summary.get("tickers_fetched", []),
            "by_operation": tracer_summary.get("by_operation", {}),
            "first_1s_calls": tracer_summary.get("first_1s_calls", 0),
            "first_5s_calls": tracer_summary.get("first_5s_calls", 0),
            "counters": tracer_summary.get("counters", {}),
        },
        "cache": {
            "age_seconds": cache_age_seconds,
        },
        "portfolio": {
            "holdings_count": holdings_count,
            "holdings_with_fresh_price": fresh_prices,
            "holdings_with_company_data": fresh_info,
            "stale_data_count": stale_data_count,
            "symbols": symbol_status,
            "data_completeness": (
                f"{fresh_info}/{holdings_count}" if holdings_count else "0/0"
            ),
        },
        "background_tasks": {
            "catalyst_polling_active": _background_task is not None and not _background_task.done(),
            "catalyst_polling_stopped": _stop_polling.is_set(),
        },
        "generated_at": datetime.utcnow().isoformat(),
    }


@app.get("/diagnostics/request-trace")
def request_trace_diagnostics():
    """Return provider call trace summary with burst detection."""
    tracer = get_request_tracer()
    return tracer.summary()


@app.get("/diagnostics/request-trace/raw")
def request_trace_raw():
    """Return raw call records for detailed analysis."""
    tracer = get_request_tracer()
    calls = tracer.get_raw_calls()
    return {"calls": calls, "total": len(calls)}


@app.get("/diagnostics/environment")
def environment_diagnostics():
    """Safe environment summary (no secrets)."""
    import os
    return {
        "platform": os.name,
        "python": __import__("sys").version.split()[0],
        "database": settings.DATABASE_URL.split("///")[-1] if "///" in settings.DATABASE_URL else "unknown",
        "data_dir": str(settings.DATA_DIR),
        "upload_dir": str(settings.UPLOAD_DIR),
        "backend_host": settings.BACKEND_HOST,
        "backend_port": settings.BACKEND_PORT,
        "cors_origins": [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
        "price_cache_ttl": settings.PRICE_CACHE_TTL,
        "fundamentals_cache_ttl": settings.FUNDAMENTALS_CACHE_TTL,
        "news_cache_ttl": settings.NEWS_CACHE_TTL,
        "analysis_cache_ttl": settings.ANALYSIS_CACHE_TTL,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global unhandled exception handler."""
    logger.error(f"Global exception caught on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Internal server error: {str(exc)}"}
    )
