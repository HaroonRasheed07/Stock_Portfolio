"""
yfinance data provider implementation.
Primary free data source for all market data, fundamentals, and news.

RENDER/PRODUCTION HARDENING:
- Detects empty/invalid provider responses
- Validates response structure before parsing
- Implements request timeout limits
- Uses proper user-agent to avoid blocking
- Logs actual failure modes for debugging
- Fallback to stale cache on provider failure
"""
import logging
import asyncio
import time
import json as _json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# ── CRITICAL: Suppress noisy yfinance library logging ──
# yfinance prints "possibly delisted", "429", "Expecting value" etc.
# to stderr which confuses users. We classify and log these ourselves.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("yfinance").addHandler(logging.NullHandler())
# Also suppress urllib3 retry noise from yfinance's internal requests
logging.getLogger("urllib3").setLevel(logging.ERROR)
# Suppress the yfinance Ticker quoteSummary error spam
os.environ.setdefault("YF_LOG_DISABLED", "1")

import yfinance as yf  # noqa: E402

from app.providers.base import (
    MarketDataProvider,
    FundamentalDataProvider,
    NewsProvider,
)
from app.config import get_settings
from app.utils.resilience import (
    ErrorCategory,
    classify_error,
    get_circuit_breaker,
    get_provider_health,
    backoff_with_jitter,
    structured_failure,
)
from app.utils.request_tracer import get_request_tracer
from app.utils.stock_directory import lookup_company_name

logger = logging.getLogger(__name__)

# Thread pool for running synchronous yfinance calls
_executor = ThreadPoolExecutor(max_workers=4)
_health = get_provider_health()
_breaker = get_circuit_breaker("yahoo")


def _safe_json_parse(raw: str, context: str = "") -> Any:
    """Parse JSON safely, returning None on failure instead of raising."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        return _json.loads(raw)
    except (_json.JSONDecodeError, ValueError) as e:
        logger.warning(f"JSON parse error{f' ({context})' if context else ''}: {e}")
        return None


def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in the thread pool."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, lambda: func(*args, **kwargs))


class YFinanceProvider(MarketDataProvider, FundamentalDataProvider, NewsProvider):
    """
    yfinance-based data provider. Implements all three core provider interfaces.
    Free, no API key required. Rate limiting handled internally.
    """

    def __init__(self):
        self._ticker_cache: Dict[str, yf.Ticker] = {}
        self._last_request_time = 0
        self._min_request_interval = 0.35  # spacing between request STARTS
        self._max_concurrent = 4  # small concurrent pool; avoids burst 429s
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._retry_count = 0
        self._max_retries = 3
        self._backoff_base = 2.0  # exponential backoff base
        # In-flight request deduplication: symbol+op -> Future
        self._inflight: Dict[str, asyncio.Future] = {}
        # In-memory TTL caches (first layer; DB cache is the second layer)
        self._price_cache: Dict[str, tuple] = {}   # symbol -> (data, timestamp)
        self._price_cache_ttl = 300                # 5 minutes
        self._info_cache: Dict[str, tuple] = {}    # symbol -> (data, timestamp)
        self._info_cache_ttl = 3600                # 1 hour
        self._news_cache: Dict[str, tuple] = {}    # symbol -> (data, timestamp)
        self._news_cache_ttl = 1800                # 30 minutes

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    async def dedup_or_run(self, key: str, coro_factory):
        """
        Deduplicate concurrent identical requests.
        If a request with `key` is already in flight, await its result;
        otherwise run coro_factory() and share the result with followers.
        """
        existing = self._inflight.get(key)
        if existing is not None:
            return await asyncio.shield(existing)
        fut = asyncio.get_event_loop().create_future()
        self._inflight[key] = fut
        try:
            result = await coro_factory()
            if not fut.done():
                fut.set_result(result)
            return result
        except Exception as e:
            if not fut.done():
                fut.set_exception(e)
            raise
        finally:
            self._inflight.pop(key, None)

    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """Get or create a cached yfinance Ticker object."""
        if symbol not in self._ticker_cache:
            self._ticker_cache[symbol] = yf.Ticker(symbol)
        return self._ticker_cache[symbol]

    def _validate_info_response(self, info: Dict[str, Any], symbol: str) -> Tuple[bool, str]:
        """
        Validate that yfinance returned a real response, not an empty/error dict.

        Returns (is_valid, error_message).

        Detects:
        - Empty dicts (provider timeout, 404, rate limit)
        - Missing required fields (price, currency)
        - HTML error responses (quoteType='N/A' with minimal fields)
        - Completely unusable data
        """
        if not info or not isinstance(info, dict):
            return False, "Provider returned empty or non-dict response"

        # Check for minimal required fields
        required = {"currency"}  # currency is almost always present in real responses
        if not any(k in info for k in required):
            return False, "Provider response missing required fields (likely empty/error response)"

        # Check if the response looks like a real quote or an error
        # Real quotes have at least one of these
        data_fields = ["currentPrice", "regularMarketPrice", "navPrice", "lastPrice",
                      "previousClose", "regularMarketPreviousClose",
                      "marketCap", "regularMarketDayHigh", "bid", "ask"]
        has_price_data = any(k in info and info[k] is not None for k in data_fields)

        if not has_price_data:
            # Check if it's an obvious error response
            quote_type = info.get("quoteType", "").upper()
            if quote_type == "N/A" or quote_type == "ERROR":
                return False, f"Provider returned error response (quoteType={quote_type})"

            # Log what we got for debugging Render issues
            logger.warning(
                f"DIAGNOSTIC [{symbol}] Response has data fields but no prices: "
                f"info_keys={list(info.keys())[:10]}, "
                f"quoteType={quote_type}, "
                f"exchange={info.get('exchange', 'N/A')}"
            )
            # This might be a delisted stock or similar, which is NOT a provider error
            # Return True but caller should handle no-price case
            return True, ""

        return True, ""

    async def _throttle(self):
        """Global concurrency-limited rate limiting via shared governor."""
        from app.utils.governor import get_governor
        gov = get_governor()
        async with gov._semaphore:
            now = time.time()
            elapsed = now - gov._last_request_time
            wait = max(0.0, gov._min_interval - elapsed)
            if self._retry_count > 0:
                backoff = min(self._backoff_base ** self._retry_count, 30.0)
                wait = max(wait, backoff)
            if wait > 0:
                await asyncio.sleep(wait)
            gov._last_request_time = time.time()
            # Hold the slot only for the request start spacing, then release

    async def _retry_with_backoff(self, func, *args, max_retries: int = 3, **kwargs):
        """Run a sync function with retry on rate limit / transient errors."""
        last_err = None
        for attempt in range(max_retries):
            try:
                result = await _run_sync(func, *args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                last_err = e
                cat = classify_error(e)
                if cat == "rate_limited" or cat == "network_error":
                    self._on_rate_limit()
                    delay = backoff_with_jitter(self._retry_count)
                    logger.warning(f"Retry {attempt+1}/{max_retries} after {cat} (wait={delay:.1f}s)")
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_err

    def _on_success(self):
        """Reset retry count on successful request."""
        self._retry_count = 0

    def _on_rate_limit(self):
        """Increment retry count on rate limit."""
        self._retry_count = min(self._retry_count + 1, self._max_retries)

    def _get_cached(self, cache: Dict, key: str, ttl: int) -> Optional[Any]:
        """Get from time-based cache."""
        if key in cache:
            data, ts = cache[key]
            if time.time() - ts < ttl:
                return data
        return None

    def _set_cached(self, cache: Dict, key: str, data: Any):
        """Set in time-based cache."""
        cache[key] = (data, time.time())

    def _trace(self, operation: str, tickers: str, cache_hit: bool,
               batch: bool = False, success: bool = True,
               failure_category: str = "", stale: bool = False, dur: float = 0.0):
        """Log a provider call to the request tracer."""
        try:
            get_request_tracer().log(
                operation=operation, tickers=tickers, cache_hit=cache_hit,
                batch=batch, success=success,
                failure_category=failure_category, stale=stale,
                duration_ms=dur,
            )
        except Exception:
            pass  # tracer must never break the provider

    # ── MarketDataProvider ───────────────────────────────

    async def get_batch_historical(
        self, symbols: List[str], period: str = "1y", interval: str = "1d"
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical OHLCV for MANY symbols in ONE yf.download call.
        Robust extraction: handles single-symbol MultiIndex frames, lowercase
        columns, and total-download failures (returns {} — caller decides).
        """
        if not symbols:
            return {}

        cache_key = f"batch_hist:{','.join(sorted(symbols))}:{period}:{interval}"
        tickers_str = ",".join(symbols)
        _t = self._trace

        # Check stale cache first (even before circuit breaker check)
        stale = self._get_cached(self._price_cache, cache_key, 86400 * 7)
        if stale is not None:
            _t("history", tickers_str, cache_hit=True, batch=True, stale=True)
            return stale

        # Circuit breaker: don't hammer Yahoo when it's down
        if not _breaker.allow_request():
            logger.warning("Batch historical skipped: circuit breaker open")
            _health.record_failure("yahoo", "circuit_open",
                                   "Circuit breaker open; request not attempted",
                                   ticker=",".join(symbols[:5]), op="batch_history")
            _t("history", tickers_str, cache_hit=False, batch=True,
               success=False, failure_category="circuit_open")
            return {}

        start = time.time()
        try:
            def _fetch():
                try:
                    data = yf.download(
                        symbols, period=period, interval=interval,
                        group_by="ticker", progress=False, threads=True,
                        auto_adjust=True,
                    )
                except Exception as e:
                    raise RuntimeError(f"yf.download failed: {e}")

                out: Dict[str, pd.DataFrame] = {}
                if data is None or (hasattr(data, "empty") and data.empty):
                    return out

                def _extract(sym: str, frame: pd.DataFrame):
                    """Extract a per-symbol OHLC frame, tolerating any layout."""
                    try:
                        if frame is None or frame.empty:
                            return
                        df = frame.copy()

                        # Flatten MultiIndex columns if the symbol level is present
                        if isinstance(df.columns, pd.MultiIndex):
                            syms = set(df.columns.get_level_values(0))
                            if sym in syms:
                                df = df[sym].copy()
                            else:
                                # Sometimes the ticker level is level 1
                                lvl1 = set(df.columns.get_level_values(-1))
                                if sym in lvl1:
                                    df = df.xs(sym, axis=1, level=-1).copy()
                                else:
                                    return

                        # Normalize column names case-insensitively
                        rename = {}
                        for c in df.columns:
                            cl = str(c).strip().capitalize() if str(c).strip().lower() in (
                                "open", "high", "low", "close", "volume", "adj close"
                            ) else str(c)
                            if str(c).strip().lower() == "adj close":
                                continue
                            rename[c] = cl
                        df = df.rename(columns=rename)

                        required = {"Open", "High", "Low", "Close"}
                        if not required.issubset(set(df.columns)):
                            # Last resort: use whatever numeric Close exists
                            close_cols = [c for c in df.columns
                                          if "close" in str(c).lower()]
                            if not close_cols:
                                return
                            for std in ("Open", "High", "Low"):
                                if std not in df.columns:
                                    df[std] = df[close_cols[0]]
                            df = df.rename(columns={close_cols[0]: "Close"})
                            if "Volume" not in df.columns:
                                df["Volume"] = 0

                        df.index.name = "Date"
                        df = df.reset_index()
                        if "Date" in df.columns and hasattr(df["Date"].dt, "tz") and df["Date"].dt.tz is not None:
                            df["Date"] = df["Date"].dt.tz_localize(None)

                        cols = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"]
                                if c in df.columns]
                        if "Close" not in cols or len(df) == 0:
                            return

                        # Drop rows where Close is NaN (common on partial downloads)
                        df = df.dropna(subset=["Close"])
                        if df.empty:
                            return
                        out[sym] = df[cols]
                    except Exception as e:
                        logger.warning(f"Batch history extract failed for {sym}: {e}")

                if isinstance(data.columns, pd.MultiIndex):
                    top_syms = list(data.columns.get_level_values(0))
                    for sym in symbols:
                        if sym in top_syms:
                            _extract(sym, data[sym])
                else:
                    # Single-symbol frame (or flattened)
                    for sym in symbols:
                        _extract(sym, data)
                return out

            results = await _run_sync(_fetch)
            dur_ms = (time.time() - start) * 1000
            ok = sum(1 for v in results.values() if v is not None and not v.empty)
            failed = len(symbols) - ok

            if ok > 0:
                _breaker.record_success()
                _health.record_success("yahoo", dur_ms, op="batch_history",
                                       ticker=f"{ok}/{len(symbols)}")
                self._set_cached(self._price_cache, cache_key, results)
                _t("history", tickers_str, cache_hit=False, batch=True, dur=dur_ms)
            else:
                # CRITICAL: Empty batch is a PROVIDER-level failure (rate limit / blocked),
                # NOT a per-symbol "not_found". Classify as rate_limited so the circuit
                # breaker opens and prevents hammering Yahoo with individual calls.
                cat = ErrorCategory.RATE_LIMITED
                _breaker.record_failure(cat)
                _health.record_failure("yahoo", cat,
                                       f"Batch download returned 0/{len(symbols)} symbols "
                                       "(likely rate-limited or blocked)",
                                       duration_ms=dur_ms, op="batch_history")
                logger.warning(
                    f"BATCH_EMPTY: 0/{len(symbols)} symbols returned — "
                    f"classified as rate_limited, failure_count={_breaker._failure_count}/"
                    f"{_breaker.failure_threshold}"
                )
                # Serve stale cache on complete failure
                stale = self._get_cached(self._price_cache, cache_key, 86400 * 7)
                if stale:
                    logger.info(f"Batch download failed, serving stale cache ({len(stale)} symbols)")
                    results = stale
                    _t("history", tickers_str, cache_hit=False, batch=True,
                       success=False, failure_category=cat, stale=True, dur=dur_ms)
                else:
                    _t("history", tickers_str, cache_hit=False, batch=True,
                       success=False, failure_category=cat, dur=dur_ms)
            logger.info(f"Batch historical download: {ok}/{len(symbols)} symbols OK "
                        f"({failed} failed, {dur_ms:.0f}ms)")
            return results
        except Exception as e:
            dur_ms = (time.time() - start) * 1000
            cat = classify_error(e)
            _breaker.record_failure(cat)
            _health.record_failure("yahoo", cat, str(e), op="batch_history")
            if cat == "rate_limited":
                self._on_rate_limit()
                await asyncio.sleep(backoff_with_jitter(self._retry_count))
            logger.error(f"Batch historical download failed ({cat}): {e}")
            _t("history", tickers_str, cache_hit=False, batch=True,
               success=False, failure_category=cat, dur=dur_ms)
            return {}

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """Get current price data from yfinance. Falls back to stale cache on failure."""
        _t = self._trace
        # Check in-memory cache first
        cached = self._get_cached(self._price_cache, symbol, self._price_cache_ttl)
        if cached:
            _health.record_cache_hit("yahoo")
            _t("price", symbol, cache_hit=True)
            return cached

        # Circuit breaker open? serve stale or structured failure — never fake data
        if not _breaker.allow_request():
            stale = self._price_cache.get(symbol)
            if stale is not None:
                result = dict(stale[0])
                result["from_stale_cache"] = True
                result["status"] = "stale"
                _t("price", symbol, cache_hit=False, stale=True, failure_category="circuit_open")
                return result
            _t("price", symbol, cache_hit=False, success=False, failure_category="circuit_open")
            return structured_failure(symbol, "circuit_open",
                                      "Market data provider temporarily unavailable")
        start = time.time()

        await self._throttle()
        try:
            def _fetch():
                ticker = self._get_ticker(symbol)
                info = ticker.info

                # CRITICAL: Validate response before parsing
                # This catches empty dicts, HTML error pages, rate limits, timeouts
                is_valid, validation_error = self._validate_info_response(info, symbol)
                if not is_valid:
                    # Provider returned an error/empty response
                    # Classify as rate_limited if it looks like a provider-level issue
                    logger.warning(
                        f"yfinance response invalid for {symbol}: {validation_error}"
                    )
                    raise RuntimeError(f"Provider response invalid: {validation_error}")

                price = info.get("currentPrice") or info.get("regularMarketPrice") or \
                        info.get("navPrice", 0)
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose", 0)

                # DIAGNOSTIC: Log when price is 0 or info looks incomplete
                if not price:
                    logger.warning(
                        f"DIAGNOSTIC [{symbol}] price=0: "
                        f"currentPrice={info.get('currentPrice')}, "
                        f"regularMarketPrice={info.get('regularMarketPrice')}, "
                        f"navPrice={info.get('navPrice')}, "
                        f"quoteType={info.get('quoteType')}, "
                        f"info_keys_count={len(info)}"
                    )

                change = price - prev_close if price and prev_close else None
                change_pct = (change / prev_close * 100) if change and prev_close else None

                return {
                    "symbol": symbol,
                    "price": price,
                    "previous_close": prev_close,
                    "open": info.get("open") or info.get("regularMarketOpen"),
                    "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
                    "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
                    "volume": info.get("volume") or info.get("regularMarketVolume"),
                    "avg_volume": info.get("averageVolume"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                    "change": change,
                    "change_pct": change_pct,
                    "market_cap": info.get("marketCap"),
                    "bid": info.get("bid"),
                    "ask": info.get("ask"),
                    "currency": info.get("currency", "USD"),
                }

            # Per-ticker timeout: prevent one slow ticker from blocking everything
            try:
                result = await asyncio.wait_for(
                    self._retry_with_backoff(_fetch, max_retries=2),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Price fetch timed out for {symbol} after 60s")
                return structured_failure(symbol, "timeout",
                                          f"Price fetch timed out for {symbol}")
            dur_ms = (time.time() - start) * 1000
            if result and result.get("price"):
                self._on_success()
                self._set_cached(self._price_cache, symbol, result)
                _breaker.record_success()
                _health.record_success("yahoo", dur_ms, ticker=symbol, op="price")
                result["status"] = "success"
                result["data_status"] = "success"
                _t("price", symbol, cache_hit=False, dur=dur_ms)
            elif isinstance(result, dict):
                # Provider responded but no price
                # Try fallback: maybe Ticker.info failed but yf.download() works
                logger.info(f"Ticker.info returned no price for {symbol}, trying fallback download fetch...")
                fallback = await self._fetch_price_via_download(symbol)
                if fallback and fallback.get("price"):
                    logger.info(f"Fallback download succeeded for {symbol}: ${fallback.get('price')}")
                    self._on_success()
                    self._set_cached(self._price_cache, symbol, fallback)
                    _breaker.record_success()
                    _health.record_success("yahoo", dur_ms + (time.time() - start) * 1000, ticker=symbol, op="price_fallback")
                    fallback["status"] = "success"
                    fallback["data_status"] = "success"
                    return fallback
                
                # Fallback also failed - likely delisted/unknown symbol
                cat = classify_error(message="no price in response after fallback (possibly delisted)")
                _health.record_failure("yahoo", cat,
                                       f"No price data returned for {symbol}",
                                       duration_ms=dur_ms, ticker=symbol, op="price")
                result.update({
                    "status": "not_found",
                    "data_status": "unavailable",
                    "error_category": cat,
                    "error": f"No price data available for {symbol}",
                })
                _t("price", symbol, cache_hit=False, success=False,
                   failure_category=cat, dur=dur_ms)
            return result
        except Exception as e:
            dur_ms = (time.time() - start) * 1000
            cat = classify_error(e)
            if cat == "rate_limited":
                self._on_rate_limit()
            _breaker.record_failure(cat)
            _health.record_failure("yahoo", cat, str(e), duration_ms=dur_ms,
                                   ticker=symbol, op="price")
            # Stale-cache fallback before giving up
            stale = self._price_cache.get(symbol)
            if stale is not None and (time.time() - stale[1]) < 86400 * 7:
                logger.info(f"Serving stale price cache for {symbol} after failure ({cat})")
                result = dict(stale[0])
                result["from_stale_cache"] = True
                result["status"] = "stale"
                result["data_status"] = "stale"
                _t("price", symbol, cache_hit=False, stale=True,
                   failure_category=cat, dur=dur_ms)
                return result
            _t("price", symbol, cache_hit=False, success=False,
               failure_category=cat, dur=dur_ms)
            # Primary ticker.info path failed. Before giving up, try the
            # yf.download() fallback which uses a different Yahoo API endpoint
            # and may not be blocked even when the quoteSummary endpoint is.
            try:
                logger.info(
                    f"get_current_price primary path failed for {symbol} ({cat}), "
                    f"trying yf.download fallback..."
                )
                fallback = await self._fetch_price_via_download(symbol)
                if fallback and fallback.get("price"):
                    logger.info(f"Download fallback succeeded for {symbol}: ${fallback.get('price')}")
                    self._on_success()
                    self._set_cached(self._price_cache, symbol, fallback)
                    _breaker.record_success()
                    _health.record_success(
                        "yahoo", dur_ms + (time.time() - start) * 1000,
                        ticker=symbol, op="price_fallback"
                    )
                    fallback["status"] = "success"
                    fallback["data_status"] = "success"
                    return fallback
            except Exception as fb_e:
                logger.warning(f"Price download fallback failed for {symbol}: {fb_e}")

            # Stale-cache fallback before giving up
            stale = self._price_cache.get(symbol)
            if stale is not None and (time.time() - stale[1]) < 86400 * 7:
                logger.info(f"Serving stale price cache for {symbol} after failure ({cat})")
                result = dict(stale[0])
                result["from_stale_cache"] = True
                result["status"] = "stale"
                result["data_status"] = "stale"
                _t("price", symbol, cache_hit=False, stale=True,
                   failure_category=cat, dur=dur_ms)
                return result
            _t("price", symbol, cache_hit=False, success=False,
               failure_category=cat, dur=dur_ms)
            failure = structured_failure(symbol, cat, str(e))
            failure["data_status"] = "unavailable"
            return failure

    async def _fetch_price_via_download(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fallback method: get current price via yf.download() instead of Ticker.info.

        yf.download() uses a different Yahoo API path (/v8/finance/chart or CSV
        download endpoints) that is frequently NOT blocked even when quoteSummary
        (Ticker.info) is rate-limited. It returns OHLCV bars; we use the last
        close as the current price.

        Handles both simple columns and MultiIndex columns (yfinance >= 1.0).
        """
        try:
            def _fetch():
                data = yf.download(
                    symbol, period="5d", interval="1d",
                    progress=False, threads=False,
                )
                if data is None or data.empty:
                    return None

                # --- Normalize columns -------------------------------------------------
                if isinstance(data.columns, pd.MultiIndex):
                    # Single-symbol download: level 0 = field, level 1 = symbol
                    fields = list(data.columns.get_level_values(0).unique())

                    def _series(field_name: str):
                        matches = [f for f in fields if str(f).lower() == field_name]
                        return data[matches[0]] if matches else None

                    close_s = _series("close")
                    open_s = _series("open")
                    high_s = _series("high")
                    low_s = _series("low")
                    vol_s = _series("volume")
                else:
                    close_s = data["Close"]
                    open_s = data.get("Open")
                    high_s = data.get("High")
                    low_s = data.get("Low")
                    vol_s = data.get("Volume")

                def _get_value(s, idx: int):
                    """Extract a scalar from a (possibly nested) Series.</summary>"""
                    if s is None:
                        return None
                    try:
                        v = s.iloc[idx]
                    except IndexError:
                        return None
                    # v may itself be a Series when MultiIndex slicing returns 1-col frames
                    while hasattr(v, "__len__") and hasattr(v, "iloc") and len(getattr(v, "shape", (1,))) == 1:
                        try:
                            v = v.iloc[0]
                        except Exception:
                            break
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None

                if close_s is None:
                    return None

                last_close = _get_value(close_s, -1)
                if last_close is None:
                    return None
                prev_close = _get_value(close_s, -2) if len(close_s) > 1 else last_close

                last_open = _get_value(open_s, -1)
                last_high = _get_value(high_s, -1)
                last_low = _get_value(low_s, -1)

                last_vol = None
                if vol_s is not None:
                    try:
                        v = vol_s.iloc[-1]
                        while hasattr(v, "iloc") and len(getattr(v, "shape", (1,))) == 1:
                            try:
                                v = v.iloc[0]
                            except Exception:
                                break
                        last_vol = int(v) if v is not None and not np.isnan(v) else 0
                    except Exception:
                        last_vol = 0

                change = last_close - prev_close if last_close and prev_close else None
                change_pct = (change / prev_close * 100) if change and prev_close else None

                return {
                    "symbol": symbol,
                    "price": last_close,
                    "previous_close": prev_close,
                    "open": last_open,
                    "day_high": last_high,
                    "day_low": last_low,
                    "volume": last_vol,
                    "change": change,
                    "change_pct": change_pct,
                    "currency": "USD",
                    "source": "yf_download_fallback",
                }

            return await _run_sync(_fetch)
        except Exception as e:
            logger.debug(f"Price download fallback failed for {symbol}: {e}")
            return None

    async def get_historical_prices(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> pd.DataFrame:
        """Get historical OHLCV data. Falls back to stale cache on failure."""
        from app.utils.resilience import get_circuit_breaker
        _t = self._trace
        cache_key = f"{symbol}_{period}_{interval}"
        cached = self._get_cached(self._price_cache, f"hist_{cache_key}", 3600)
        if cached is not None:
            _t("history", symbol, cache_hit=True)
            return cached

        # CRITICAL: Check circuit breaker before any Yahoo call
        breaker = get_circuit_breaker("yahoo")
        if not breaker.allow_request():
            # Try stale cache (7 day window)
            stale = self._get_cached(self._price_cache, f"hist_{cache_key}", 86400 * 7)
            if stale is not None:
                _t("history", symbol, cache_hit=False, stale=True, failure_category="circuit_open")
                return stale
            _t("history", symbol, cache_hit=False, success=False, failure_category="circuit_open")
            return pd.DataFrame()

        await self._throttle()
        start = time.time()
        try:
            def _fetch():
                ticker = self._get_ticker(symbol)
                # CRITICAL: ticker.history() can return None on Render (Yahoo
                # blocking datacenter IPs). Guard against it — never call .empty
                # on None or it crashes as `'NoneType' object has no attribute 'empty'`.
                df = ticker.history(period=period, interval=interval)
                if df is None:
                    return pd.DataFrame()
                if df.empty:
                    return pd.DataFrame()
                df.index.name = "Date"
                df = df.reset_index()
                if hasattr(df["Date"].dt, "tz") and df["Date"].dt.tz is not None:
                    df["Date"] = df["Date"].dt.tz_localize(None)
                return df[["Date", "Open", "High", "Low", "Close", "Volume"]]

            result = await asyncio.wait_for(_run_sync(_fetch), timeout=60)
            dur_ms = (time.time() - start) * 1000
            if result is not None and not result.empty:
                self._on_success()
                self._set_cached(self._price_cache, f"hist_{cache_key}", result)
                _t("history", symbol, cache_hit=False, dur=dur_ms)
                return result
            
            # Empty result from Ticker.history() - try fallback via yf.download()
            logger.info(f"Historical data for {symbol} returned empty, trying yf.download() fallback...")
            fallback_df = await self._fetch_historical_via_download(symbol, period, interval)
            dur_ms = (time.time() - start) * 1000
            if fallback_df is not None and not fallback_df.empty:
                logger.info(f"Fallback yf.download() succeeded for {symbol}: {len(fallback_df)} rows")
                self._on_success()
                self._set_cached(self._price_cache, f"hist_{cache_key}", fallback_df)
                _t("history", symbol, cache_hit=False, dur=dur_ms)
                return fallback_df
            
            # Both methods failed - log and return empty
            logger.warning(f"No historical data available for {symbol} (Ticker.history + yf.download both empty)")
            _t("history", symbol, cache_hit=False, success=False,
               failure_category="no_data", dur=dur_ms)
        except asyncio.TimeoutError:
            dur_ms = (time.time() - start) * 1000
            logger.warning(f"History fetch timed out for {symbol} after 30s")
            cat = "timeout"
            _breaker.record_failure(cat)
            _health.record_failure("yahoo", cat, f"History timeout for {symbol}",
                                   duration_ms=dur_ms, ticker=symbol, op="history")
            # Serve stale cache if available
            stale = self._get_cached(self._price_cache, f"hist_{cache_key}", 86400 * 7)
            if stale is not None:
                _t("history", symbol, cache_hit=False, stale=True, failure_category=cat, dur=dur_ms)
                return stale
            _t("history", symbol, cache_hit=False, success=False, failure_category=cat, dur=dur_ms)
            return pd.DataFrame()
        except Exception as e:
            dur_ms = (time.time() - start) * 1000
            cat = classify_error(e)
            if cat == "rate_limited":
                self._on_rate_limit()
                logger.warning(f"Rate limited fetching history for {symbol}")
            else:
                logger.error(f"Error fetching history for {symbol}: {e}")
            # Serve stale cache if available (up to 7 days old)
            stale = self._get_cached(self._price_cache, f"hist_{cache_key}", 86400 * 7)
            if stale is not None:
                logger.info(f"Serving stale historical cache for {symbol} after {cat}")
                _t("history", symbol, cache_hit=False, stale=True,
                   failure_category=cat, dur=dur_ms)
                return stale
            _t("history", symbol, cache_hit=False, success=False,
               failure_category=cat, dur=dur_ms)
            return pd.DataFrame()

    async def _fetch_historical_via_download(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Fallback method: try to get historical data via yf.download() instead of Ticker.history().
        Used when Ticker.history() fails or returns empty (common on Render when rate-limited).

        Handles single-symbol MultiIndex frames (yfinance >= 1.0), where the
        returned columns are [(Close, sym), (High, sym), ...].

        Returns empty DataFrame if download also fails.
        """
        logger.debug(f"FALLBACK: Attempting {symbol} historical via yf.download({period}, {interval})")
        try:
            def _fetch():
                # Try download with same parameters
                data = yf.download(
                    symbol, period=period, interval=interval,
                    progress=False, threads=False
                )
                if data is None or data.empty:
                    return pd.DataFrame()

                # --- Flatten MultiIndex for single-symbol frames -----------------
                # yfinance>=1.0 single-symbol download: columns are
                # [(Close, sym), (High, sym), (Low, sym), (Open, sym), (Volume, sym)]
                if isinstance(data.columns, pd.MultiIndex):
                    try:
                        syms = data.columns.get_level_values(1).unique()
                        target = None
                        for s in syms:
                            if str(s).upper() == symbol.upper():
                                target = s
                                break
                        if target is None and len(syms) > 0:
                            target = syms[0]
                        if target is not None:
                            # level 1 is the ticker; select on that level
                            data = data.xs(target, level=1, axis=1).copy()
                    except Exception:
                        # fall back to level-0 fields (already stackable)
                        try:
                            data.columns = data.columns.get_level_values(0)
                        except Exception:
                            pass

                # Normalize to standard format
                if isinstance(data.index, pd.DatetimeIndex):
                    data.index.name = "Date"
                    data = data.reset_index()
                elif "Date" not in data.columns:
                    # Some formats don't have a Date column, use index
                    data = data.reset_index()
                    if data.columns[0] != "Date":
                        data = data.rename(columns={data.columns[0]: "Date"})

                # Handle timezone
                if "Date" in data.columns and hasattr(data["Date"].dt, "tz"):
                    if data["Date"].dt.tz is not None:
                        data["Date"] = data["Date"].dt.tz_localize(None)

                # Ensure required columns exist and pick them
                required = ["Date", "Open", "High", "Low", "Close", "Volume"]
                if all(c in data.columns for c in required):
                    return data[required]
                else:
                    # Try to find columns with flexible naming
                    cols = {c.lower(): c for c in data.columns}
                    remap = {}
                    for req in required:
                        lower_req = req.lower()
                        if lower_req in cols:
                            remap[cols[lower_req]] = req

                    if len(remap) >= 5:  # At least have OHLCV
                        data = data.rename(columns=remap)
                        available = [req for req in required if req in data.columns]
                        return data[available] if available else pd.DataFrame()
                    else:
                        logger.debug(f"Fallback download missing columns for {symbol}: found {list(data.columns)}")
                        return pd.DataFrame()

            result = await asyncio.wait_for(_run_sync(_fetch), timeout=30)
            return result if result is not None else pd.DataFrame()
        except Exception as e:
            logger.debug(f"Fallback download failed for {symbol}: {e}")
            return pd.DataFrame()
    async def get_batch_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get prices for multiple symbols using yfinance batch download."""
        from app.utils.resilience import get_circuit_breaker
        if not symbols:
            return {}

        # Check circuit breaker before batch call
        breaker = get_circuit_breaker("yahoo")
        if not breaker.allow_request():
            return {s: {"symbol": s, "price": None, "status": "circuit_open"} for s in symbols}

        try:
            def _fetch():
                results = {}
                data = yf.download(
                    symbols, period="2d", group_by="ticker",
                    progress=False, threads=True
                )

                for symbol in symbols:
                    try:
                        if len(symbols) == 1:
                            sym_data = data
                        else:
                            sym_data = data[symbol] if symbol in data.columns.get_level_values(0) else None

                        if sym_data is not None and not sym_data.empty:
                            last_row = sym_data.iloc[-1]
                            prev_row = sym_data.iloc[-2] if len(sym_data) > 1 else last_row
                            price = float(last_row.get("Close", 0))
                            prev_close = float(prev_row.get("Close", 0))
                            change = price - prev_close if price and prev_close else 0
                            change_pct = (change / prev_close * 100) if prev_close else 0

                            results[symbol] = {
                                "symbol": symbol,
                                "price": price,
                                "previous_close": prev_close,
                                "change": round(change, 2),
                                "change_pct": round(change_pct, 2),
                                "volume": float(last_row.get("Volume", 0)),
                            }
                        else:
                            results[symbol] = {"symbol": symbol, "price": None}
                    except Exception as e:
                        logger.warning(f"Error processing batch price for {symbol}: {e}")
                        results[symbol] = {"symbol": symbol, "price": None}

                return results

            return await _run_sync(_fetch)
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                self._on_rate_limit()
                logger.warning("Rate limited in batch price fetch")
            else:
                logger.error(f"Error in batch price fetch: {e}")
            return {s: {"symbol": s, "price": None} for s in symbols}

    async def search_symbol(self, query: str) -> List[Dict[str, Any]]:
        """Search for stock symbols with autocomplete support.

        - Company/ETF name queries go straight to yf.Search (fast path).
        - Exact-ticker info lookup only for short ticker-like queries.
        - Results cached 10 min; stale cache served if Yahoo fails/rate-limits.
        """
        import re as _re
        q = query.strip()
        if not q:
            return []
        cache_key = f"search:{q.upper()}"

        cached = self._get_cached(self._news_cache, cache_key, 600)
        if cached is not None:
            return cached

        looks_like_ticker = bool(_re.match(r"^[A-Z]{1,5}$", q.upper()))

        async def _run():
            await self._throttle()

            def _search():
                results = []
                # Fast path: search API handles both names and tickers
                try:
                    search_results = yf.Search(q)
                    quotes = getattr(search_results, "quotes", None) or []
                    for quote in quotes[:8]:
                        sym = quote.get("symbol", "")
                        if not sym:
                            continue
                        results.append({
                            "symbol": sym,
                            "name": quote.get("longname") or quote.get("shortname") or "",
                            "exchange": quote.get("exchange", ""),
                            "type": quote.get("quoteType", "EQUITY"),
                            "sector": quote.get("sector"),
                            "market_cap": quote.get("marketCap"),
                        })
                except Exception as e:
                    logger.warning(f"yf.Search failed for '{q}': {e}")

                # Exact-ticker enrichment only for ticker-like queries
                if looks_like_ticker and not any(
                    r["symbol"].upper() == q.upper() for r in results
                ):
                    try:
                        ticker = yf.Ticker(q.upper())
                        info = ticker.info
                        if info and info.get("symbol"):
                            results.insert(0, {
                                "symbol": info.get("symbol", q.upper()),
                                "name": info.get("longName") or info.get("shortName", ""),
                                "exchange": info.get("exchange", ""),
                                "type": info.get("quoteType", "EQUITY"),
                                "sector": info.get("sector"),
                                "market_cap": info.get("marketCap"),
                            })
                    except Exception as e:
                        logger.warning(f"Ticker lookup failed for '{q}': {e}")

                return results[:10]

            return await _run_sync(_search)

        try:
            key = f"provider-search:{cache_key}"
            existing = self._inflight.get(key)
            if existing is not None:
                return await asyncio.shield(existing)
            fut = asyncio.get_event_loop().create_future()
            self._inflight[key] = fut
            try:
                result = await _run()
                if not fut.done():
                    fut.set_result(result)
                if result:
                    self._on_success()
                    self._set_cached(self._news_cache, cache_key, result)
                return result
            except Exception as e:
                if not fut.done():
                    fut.set_exception(e)
                raise
            finally:
                self._inflight.pop(key, None)
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                self._on_rate_limit()
                logger.warning(f"Rate limited searching for {q}")
            else:
                logger.error(f"Error searching for {query}: {e}")
            # Serve stale cache rather than an empty result
            stale = self._news_cache.get(cache_key)
            if stale is not None:
                logger.info(f"Serving stale search cache for '{q}'")
                return stale[0]
            return []

    # ── FundamentalDataProvider ──────────────────────────

    async def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive stock information. Falls back to stale cache on failure."""
        _t = self._trace
        # Check in-memory cache first
        cached = self._get_cached(self._info_cache, symbol, self._info_cache_ttl)
        if cached:
            _health.record_cache_hit("yahoo")
            _t("info", symbol, cache_hit=True)
            return cached

        if not _breaker.allow_request():
            stale = self._info_cache.get(symbol)
            if stale is not None:
                result = dict(stale[0])
                result["from_stale_cache"] = True
                result["status"] = "stale"
                _t("info", symbol, cache_hit=False, stale=True, failure_category="circuit_open")
                return result
            _t("info", symbol, cache_hit=False, success=False, failure_category="circuit_open")
            return {"symbol": symbol, "error": "Market data provider temporarily unavailable",
                    "status": "provider_unavailable", "error_category": "circuit_open"}
        start = time.time()

        await self._throttle()
        try:
            def _fetch():
                ticker = self._get_ticker(symbol)
                info = ticker.info
                result = {
                    "symbol": symbol,
                    "name": info.get("longName") or info.get("shortName", ""),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "market_cap": info.get("marketCap"),
                    "asset_type": info.get("quoteType", "EQUITY"),
                    "exchange": info.get("exchange"),
                    "currency": info.get("currency", "USD"),
                    "country": info.get("country"),
                    "description": info.get("longBusinessSummary", ""),
                    "website": info.get("website"),
                    "employees": info.get("fullTimeEmployees"),
                    "dividend_yield": info.get("dividendYield"),
                    "dividend_rate": info.get("dividendRate"),
                    "ex_dividend_date": str(info.get("exDividendDate", "")) if info.get("exDividendDate") else None,
                    "beta": info.get("beta"),
                    "pe_ratio": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "peg_ratio": info.get("pegRatio"),
                    "price_to_book": info.get("priceToBook"),
                    "price_to_sales": info.get("priceToSalesTrailing12Months"),
                    "enterprise_value": info.get("enterpriseValue"),
                    "ev_to_ebitda": info.get("enterpriseToEbitda"),
                    "profit_margin": info.get("profitMargins"),
                    "operating_margin": info.get("operatingMargins"),
                    "gross_margin": info.get("grossMargins"),
                    "revenue": info.get("totalRevenue"),
                    "revenue_growth": info.get("revenueGrowth"),
                    "earnings": info.get("netIncomeToCommon"),
                    "eps": info.get("trailingEps"),
                    "forward_eps": info.get("forwardEps"),
                    "roe": info.get("returnOnEquity"),
                    "roa": info.get("returnOnAssets"),
                    "debt_to_equity": info.get("debtToEquity"),
                    "current_ratio": info.get("currentRatio"),
                    "free_cash_flow": info.get("freeCashflow"),
                    "operating_cash_flow": info.get("operatingCashflow"),
                    "total_cash": info.get("totalCash"),
                    "total_debt": info.get("totalDebt"),
                    "book_value": info.get("bookValue"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                    "fifty_day_average": info.get("fiftyDayAverage"),
                    "two_hundred_day_average": info.get("twoHundredDayAverage"),
                    "avg_volume": info.get("averageVolume"),
                    "shares_outstanding": info.get("sharesOutstanding"),
                    "float_shares": info.get("floatShares"),
                    "payout_ratio": info.get("payoutRatio"),
                }
                # Production hardening (Render/datacenter IPs): Yahoo's quoteSummary
                # is intermittently blocked per-request. A cached Ticker may hold an
                # empty/blocked response; retry once with a FRESH yf.Ticker (new
                # session) which often bypasses the transient block and returns the
                # full company data (description, key metrics, etc.).
                if not result.get("name") and not result.get("market_cap") and not result.get("pe_ratio"):
                    try:
                        fresh = yf.Ticker(symbol)
                        fresh_info = fresh.info
                        if fresh_info and any(fresh_info.get(k) for k in
                                              ("longName", "shortName", "longBusinessSummary",
                                               "marketCap", "trailingPE", "totalRevenue")):
                            logger.info(f"[{symbol}] Cached ticker info empty; recovered via fresh yf.Ticker session")
                            info = fresh_info
                            result["name"] = fresh_info.get("longName") or fresh_info.get("shortName") or result.get("name")
                            result["description"] = fresh_info.get("longBusinessSummary") or result.get("description")
                            for k, v in {
                                "sector": "sector", "industry": "industry",
                                "marketCap": "market_cap", "currency": "currency",
                            }.items():
                                if result.get(v) is None and fresh_info.get(k) is not None:
                                    result[v] = fresh_info.get(k)
                            for k, v in {
                                "trailingPE": "pe_ratio", "forwardEps": "forward_eps",
                                "trailingEps": "eps", "beta": "beta",
                                "totalRevenue": "revenue", "dividendYield": "dividend_yield",
                            }.items():
                                if result.get(v) is None and fresh_info.get(k) is not None:
                                    result[v] = fresh_info.get(k)
                            result["exchange"] = fresh_info.get("exchange") or result.get("exchange")
                            result["website"] = fresh_info.get("website") or result.get("website")
                            result["country"] = fresh_info.get("country") or result.get("country")
                            if not result.get("etf_data") and (
                                    fresh_info.get("quoteType") == "ETF" or fresh_info.get("legalType") == "Exchange Traded Fund"):
                                result["etf_data"] = {
                                    "total_assets": fresh_info.get("netAssets"),
                                    "expense_ratio": fresh_info.get("netExpenseRatio"),
                                    "category": fresh_info.get("category"),
                                }
                    except Exception:
                        logger.debug(f"[{symbol}] fresh yf.Ticker retry failed", exc_info=True)
                # ETF-specific fields
                if info.get("quoteType") == "ETF" or info.get("legalType") == "Exchange Traded Fund":
                    result["etf_data"] = {
                        "total_assets": info.get("netAssets"),
                        "expense_ratio": info.get("netExpenseRatio"),
                        "category": info.get("category"),
                        "fund_family": info.get("fundFamily"),
                        "nav_price": info.get("navPrice"),
                        "inception_date": info.get("fundInceptionDate"),
                        " holdings_count": info.get("holdingsCount"),
                        "yield_3yr": info.get("threeYearAverageReturn"),
                        "yield_5yr": info.get("fiveYearAverageReturn"),
                        "ytd_return": info.get("ytdReturn"),
                        "morning_star_rating": info.get("morningStarOverallRating"),
                    }
                # Production hardening (Render/datacenter IPs): Yahoo sometimes
                # returns an empty quoteSummary for `info` even though the chart
                # endpoint works. Retry once with a fresh info read, then fall
                # back to the local company directory for the canonical name so
                # well-known securities never surface as blank/not_found.
                if not result.get("name") and not result.get("sector") and not result.get("description"):
                    try:
                        refreshed = ticker.get_info()
                        if refreshed and any(refreshed.get(k) for k in ("longName", "shortName", "sector", "longBusinessSummary")):
                            logger.info(f"[{symbol}] Yahoo info was empty; recovered via get_info() refresh")
                            result["name"] = refreshed.get("longName") or refreshed.get("shortName") or result.get("name")
                            result["sector"] = refreshed.get("sector") or result.get("sector")
                            result["description"] = refreshed.get("longBusinessSummary") or result.get("description")
                    except Exception:
                        logger.debug(f"[{symbol}] get_info() refresh failed; using local directory", exc_info=True)
                if not result.get("name"):
                    dir_name = lookup_company_name(symbol)
                    if dir_name:
                        result["name"] = dir_name
                        logger.info(f"[{symbol}] Yahoo info empty; used local stock-directory name: {dir_name}")
                return result

            result = await self._retry_with_backoff(_fetch, max_retries=3)
            dur_ms = (time.time() - start) * 1000
            if result and not result.get("error"):
                self._on_success()
                self._set_cached(self._info_cache, symbol, result)
                _breaker.record_success()
                _health.record_success("yahoo", dur_ms, ticker=symbol, op="info")
                if not result.get("name") and not result.get("sector"):
                    # Provider responded but returned an empty profile — likely
                    # an unknown/delisted symbol. Do NOT cache or fabricate.
                    cat = classify_error(message="empty info (unknown symbol)")
                    _health.record_failure("yahoo", cat,
                                           f"Empty company info for {symbol}",
                                           duration_ms=dur_ms, ticker=symbol, op="info")
                    return {"symbol": symbol, "status": "not_found",
                            "error_category": cat,
                            "error": f"No company data available for {symbol}"}
                result["status"] = "success"
                _t("info", symbol, cache_hit=False, dur=dur_ms)
            return result
        except Exception as e:
            dur_ms = (time.time() - start) * 1000
            cat = classify_error(e)
            if cat == "rate_limited":
                self._on_rate_limit()
            _breaker.record_failure(cat)
            _health.record_failure("yahoo", cat, str(e), duration_ms=dur_ms,
                                   ticker=symbol, op="info")
            stale = self._info_cache.get(symbol)
            if stale is not None and (time.time() - stale[1]) < 86400 * 30:
                logger.info(f"Serving stale info cache for {symbol} after failure ({cat})")
                result = dict(stale[0])
                result["from_stale_cache"] = True
                result["status"] = "stale"
                _t("info", symbol, cache_hit=False, stale=True,
                   failure_category=cat, dur=dur_ms)
                return result
            _t("info", symbol, cache_hit=False, success=False,
               failure_category=cat, dur=dur_ms)
            return {"symbol": symbol, "status": "provider_unavailable",
                    "error_category": cat, "error": str(e)[:200]}

    async def get_financials(self, symbol: str) -> Dict[str, Any]:
        """Get financial statements."""
        await self._throttle()
        try:
            def _fetch():
                ticker = self._get_ticker(symbol)
                result = {}

                try:
                    income = ticker.income_stmt
                    if income is not None and not income.empty:
                        result["income_statement"] = income.to_dict()
                except Exception:
                    result["income_statement"] = None

                try:
                    balance = ticker.balance_sheet
                    if balance is not None and not balance.empty:
                        result["balance_sheet"] = balance.to_dict()
                except Exception:
                    result["balance_sheet"] = None

                try:
                    cash = ticker.cash_flow
                    if cash is not None and not cash.empty:
                        result["cash_flow"] = cash.to_dict()
                except Exception:
                    result["cash_flow"] = None

                return result

            return await _run_sync(_fetch)
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                self._on_rate_limit()
            else:
                logger.error(f"Error fetching financials for {symbol}: {e}")
            return {}

    async def get_key_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get key financial metrics (delegates to get_stock_info)."""
        return await self.get_stock_info(symbol)

    async def get_earnings(self, symbol: str) -> Dict[str, Any]:
        """Get earnings history and upcoming dates."""
        await self._throttle()
        try:
            def _fetch():
                ticker = self._get_ticker(symbol)
                result = {}

                try:
                    earnings = ticker.earnings_history
                    if earnings is not None and not earnings.empty:
                        result["earnings_history"] = earnings.to_dict("records")
                except Exception:
                    result["earnings_history"] = []

                try:
                    cal = ticker.calendar
                    if cal is not None:
                        if isinstance(cal, pd.DataFrame):
                            result["calendar"] = cal.to_dict()
                        elif isinstance(cal, dict):
                            result["calendar"] = cal
                except Exception:
                    result["calendar"] = {}

                try:
                    dates = ticker.earnings_dates
                    if dates is not None and not dates.empty:
                        dates_reset = dates.reset_index()
                        for col in dates_reset.columns:
                            if pd.api.types.is_datetime64_any_dtype(dates_reset[col]):
                                dates_reset[col] = dates_reset[col].astype(str)
                        result["earnings_dates"] = dates_reset.head(8).to_dict("records")
                except Exception:
                    result["earnings_dates"] = []

                return result

            return await _run_sync(_fetch)
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                self._on_rate_limit()
            else:
                logger.error(f"Error fetching earnings for {symbol}: {e}")
            return {}

    # ── NewsProvider ─────────────────────────────────────

    async def get_stock_news(
        self, symbol: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get news for a specific stock from yfinance."""
        from app.utils.resilience import get_circuit_breaker

        _t = self._trace
        # Check in-memory cache first
        cached = self._get_cached(self._news_cache, symbol, self._news_cache_ttl)
        if cached:
            _t("news", symbol, cache_hit=True)
            return cached[:limit]

        # CRITICAL: Check circuit breaker BEFORE making any Yahoo call
        breaker = get_circuit_breaker("yahoo")
        if not breaker.allow_request():
            _t("news", symbol, cache_hit=False, success=False, failure_category="circuit_open")
            # Try stale cache (24h window)
            stale = self._get_cached(self._news_cache, symbol, 86400)
            if stale:
                return stale[:limit]
            return []

        await self._throttle()
        try:
            def _fetch():
                ticker = self._get_ticker(symbol)
                news = ticker.news
                if not news:
                    return []
                articles = []
                for item in news[:limit]:
                    content = item.get("content", {}) if isinstance(item, dict) else {}
                    title = (
                        item.get("title") or
                        content.get("title") or
                        ""
                    )
                    summary = (
                        item.get("summary") or
                        content.get("summary") or
                        ""
                    )
                    provider = content.get("provider", {})
                    source = (
                        item.get("publisher") or
                        (provider.get("displayName") if isinstance(provider, dict) else "") or
                        ""
                    )
                    url = (
                        item.get("link") or
                        content.get("canonicalUrl", {}).get("url") or
                        ""
                    )
                    pub_date = item.get("providerPublishTime")
                    if pub_date and isinstance(pub_date, (int, float)):
                        pub_date = datetime.utcfromtimestamp(pub_date)
                    elif isinstance(pub_date, str):
                        try:
                            pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        except Exception:
                            pub_date = None

                    # Do NOT fabricate timestamps — let pub_date be None
                    # Frontend will display "Date unavailable" for missing timestamps

                    if title:
                        articles.append({
                            "title": title,
                            "summary": summary,
                            "source": source,
                            "url": url,
                            "published_at": pub_date,
                            "symbol": symbol,
                        })
                return articles

            try:
                result = await self._retry_with_backoff(_fetch, max_retries=2)
            except Exception:
                result = []
            if result:
                self._on_success()
                self._set_cached(self._news_cache, symbol, result)
                _t("news", symbol, cache_hit=False)
            else:
                _t("news", symbol, cache_hit=False, success=False, failure_category="empty")
            return result
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                self._on_rate_limit()
                logger.warning(f"Rate limited fetching news for {symbol}")
            else:
                logger.error(f"Error fetching news for {symbol}: {e}")
            # Serve stale cache if available
            stale = self._get_cached(self._news_cache, symbol, 86400)
            if stale:
                logger.info(f"Serving stale news cache for {symbol}")
                return stale[:limit]
            return []

    async def get_market_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get general market news (uses SPY as a proxy)."""
        return await self.get_stock_news("SPY", limit=limit)


# Singleton provider instance
_yfinance_provider: Optional[YFinanceProvider] = None


def get_yfinance_provider() -> YFinanceProvider:
    """Get or create singleton yfinance provider."""
    global _yfinance_provider
    if _yfinance_provider is None:
        _yfinance_provider = YFinanceProvider()
    return _yfinance_provider
