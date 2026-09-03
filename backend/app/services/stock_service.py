"""
Stock service — handles individual stock data retrieval with caching.
"""
import logging
import time
import asyncio
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.utils.cache import CacheManager
from app.providers.yfinance_provider import get_yfinance_provider
from app.services.ticker_service import get_ticker_service

logger = logging.getLogger(__name__)

# In-memory TTL cache for earnings (avoids repeated yfinance calls)
_earnings_cache: Dict[str, tuple] = {}  # symbol -> (data, timestamp)
_EARNINGS_TTL = 1800  # 30 minutes

# Max concurrent individual fallback requests to prevent request storms
_MAX_FALLBACK_CONCURRENCY = 3


class StockService:
    """Manages individual stock data operations."""

    # CRITICAL: Class-level in-flight dict shared across ALL instances
    # This ensures deduplication works across concurrent requests
    _inflight: Dict[str, asyncio.Future] = {}

    def __init__(self, db: Session):
        self.db = db
        self.cache = CacheManager(db)
        self.provider = get_yfinance_provider()
        self._ticker_service = get_ticker_service()

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize ticker symbol using centralized service."""
        return self._ticker_service.normalize(symbol)

    async def _dedup(self, key: str, coro_factory):
        """Deduplicate concurrent identical requests at service level.
        
        CRITICAL: If the first request fails, waiters get a chance to retry
        instead of all receiving the same failure.
        """
        existing = self._inflight.get(key)
        if existing is not None:
            try:
                return await asyncio.shield(existing)
            except Exception:
                # First request failed — don't propagate failure to waiters
                # Remove stale entry and let waiter retry
                self._inflight.pop(key, None)
                # Fall through to create a new request
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

    @staticmethod
    def _df_to_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Convert OHLC DataFrame to row dicts (shared by single & batch paths).
        
        Returns data in ASCENDING date order with no duplicate dates.
        Required by the lightweight-charts candlestick library.
        """
        data = []
        seen_dates = set()
        for _, row in df.iterrows():
            open_val, high_val = row.get("Open"), row.get("High")
            low_val, close_val = row.get("Low"), row.get("Close")
            if pd.isna(open_val) or pd.isna(high_val) or pd.isna(low_val) or pd.isna(close_val):
                continue
            vol = row.get("Volume", 0)
            date_val = row.get("Date")
            date_str = date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val)
            # Extract date-only for deduplication (ignore time component)
            date_key = date_str.split("T")[0] if "T" in date_str else date_str[:10]
            if date_key in seen_dates:
                continue
            seen_dates.add(date_key)
            data.append({
                "date": date_str,
                "open": round(float(open_val), 2),
                "high": round(float(high_val), 2),
                "low": round(float(low_val), 2),
                "close": round(float(close_val), 2),
                "volume": int(vol) if pd.notna(vol) else 0,
            })
        # Sort ascending by date (oldest first) — required by chart library
        data.sort(key=lambda r: r["date"])
        return data

    async def get_stock_price(self, symbol: str) -> Dict[str, Any]:
        """Get current stock price with caching + in-flight deduplication."""
        canonical = self._normalize_symbol(symbol)
        # Check cache first
        cached = self.cache.get_cached_price(canonical)
        if cached:
            cached["source"] = "cache"
            # Propagate data_status from cache: if price is 0, mark unavailable
            if not cached.get("price"):
                cached["data_status"] = "unavailable"
            elif not cached.get("data_status"):
                cached["data_status"] = "success"
            return cached

        async def _fetch():
            data = await self.provider.get_current_price(canonical)
            if data.get("price"):
                self.cache.set_cached_price(canonical, data)
                data["source"] = "live"
            else:
                # Price is 0 or missing — propagate data_status
                if not data.get("data_status"):
                    data["data_status"] = "unavailable"
            return data

        return await self._dedup(f"price:{canonical}", _fetch)

    async def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive stock info with caching + in-flight deduplication."""
        canonical = self._normalize_symbol(symbol)
        cached = self.cache.get_cached_stock_info(canonical)
        if cached:
            cached["source"] = "cache"
            # A cached name-only entry (no description/metrics) is a stale partial
            # response captured during an intermittent Yahoo block. Don't serve it
            # as if complete — re-fetch so a recovered Yahoo can fill it in.
            if self._info_has_company_data(cached):
                return cached

        async def _fetch():
            data = await self.provider.get_stock_info(canonical)
            if data and not data.get("error"):
                # Only cache genuinely useful company data. Yahoo intermittently
                # returns a name-only (metrics/description empty) response on
                # datacenter IPs. Caching that would pin a stock to "N/A" for the
                # full TTL even after Yahoo recovers, so we serve it without caching
                # and let a later complete fetch overwrite stale/full entries.
                if self._info_has_company_data(data):
                    self.cache.set_cached_stock_info(canonical, data)
                data["source"] = "live"
            return data

        return await self._dedup(f"info:{canonical}", _fetch)

    @staticmethod
    def _info_has_company_data(data: Dict[str, Any]) -> bool:
        """True when a stock-info result contains real company data worth caching.

        A blocked/partial Yahoo response yields at most a name (from the local
        directory fallback) but no description, market cap, valuation, or
        earnings figures. We only cache results that include such content.
        """
        if not isinstance(data, dict):
            return False
        if data.get("description"):
            return True
        for key in ("market_cap", "pe_ratio", "eps", "revenue", "beta", "forward_pe"):
            if data.get(key) not in (None, "", 0):
                return True
        return False

    async def get_stock_overview(self, symbol: str) -> Dict[str, Any]:
        """Get combined overview: info + price + fundamentals summary."""
        canonical = self._normalize_symbol(symbol)
        info = await self.get_stock_info(canonical)
        price = await self.get_stock_price(canonical)

        # Propagate data_status from price into overview
        price_data_status = price.get("data_status", "success" if price.get("price") else "unavailable")

        return {
            "symbol": canonical,
            "name": info.get("name", ""),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("market_cap"),
            "description": info.get("description"),
            "website": info.get("website"),
            "employees": info.get("employees"),
            "country": info.get("country"),
            "asset_type": info.get("asset_type"),
            "exchange": info.get("exchange"),
            "price": price,
            "data_status": price_data_status,
            "etf_data": info.get("etf_data"),
            "key_metrics": {
                "pe_ratio": info.get("pe_ratio"),
                "forward_pe": info.get("forward_pe"),
                "peg_ratio": info.get("peg_ratio"),
                "price_to_book": info.get("price_to_book"),
                "price_to_sales": info.get("price_to_sales"),
                "ev_to_ebitda": info.get("ev_to_ebitda"),
                "profit_margin": info.get("profit_margin"),
                "operating_margin": info.get("operating_margin"),
                "roe": info.get("roe"),
                "roa": info.get("roa"),
                "debt_to_equity": info.get("debt_to_equity"),
                "revenue": info.get("revenue"),
                "revenue_growth": info.get("revenue_growth"),
                "earnings": info.get("earnings"),
                "eps": info.get("eps"),
                "dividend_yield": info.get("dividend_yield"),
                "beta": info.get("beta"),
                "free_cash_flow": info.get("free_cash_flow"),
            },
        }

    async def get_historical_prices(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> List[Dict[str, Any]]:
        """Get historical price data with caching + in-flight deduplication."""
        canonical = self._normalize_symbol(symbol)
        cache_key = f"hist:{canonical}:{period}:{interval}"
        cached = self.cache.get_cached_historical(canonical, period)
        if cached:
            return cached

        async def _fetch():
            df = await self.provider.get_historical_prices(canonical, period, interval)
            if df.empty:
                return []
            data = self._df_to_rows(df)
            if data:
                self.cache.set_cached_historical(canonical, period, data)
            return data

        return await self._dedup(cache_key, _fetch)

    async def get_batch_historical_prices(
        self, symbols: List[str], period: str = "1y"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get historical prices for many symbols efficiently.
        Serves from DB cache where fresh; fetches ALL misses in ONE batched
        yfinance download; caches each result.

        CRITICAL RESILIENCE (3-tier fallback):
        1. Full batch download (25 symbols)
        2. Smaller batch groups (5 symbols each) if full batch fails
        3. Individual per-symbol fetch if smaller batches fail
        4. Stale DB cache as final fallback
        """
        from app.utils.resilience import get_circuit_breaker

        canonical_symbols = [self._normalize_symbol(s) for s in symbols]
        result: Dict[str, List[Dict[str, Any]]] = {}
        missing: List[str] = []

        for sym in canonical_symbols:
            cached = self.cache.get_cached_historical(sym, period)
            if cached:
                result[sym] = cached
            else:
                missing.append(sym)

        if not missing:
            logger.info(f"Batch historical: all {len(symbols)} symbols served from cache")
            return result

        logger.info(
            f"BATCH_HISTORICAL_START: requested={len(symbols)} cached={len(result)} "
            f"missing={len(missing)} symbols={','.join(missing[:10])}{'...' if len(missing) > 10 else ''}"
        )

        # Check circuit breaker BEFORE attempting batch
        breaker = get_circuit_breaker("yahoo")
        if not breaker.allow_request():
            logger.warning(
                f"BATCH_HISTORICAL: circuit breaker OPEN. "
                f"{len(missing)} symbols — trying per-symbol fallback."
            )
        else:
            # ── TIER 1: Full batch download ──────────────────────
            t0 = time.time()
            try:
                frames = await self.provider.get_batch_historical(missing, period=period)
                elapsed = time.time() - t0
                ok_count = 0
                for sym, df in frames.items():
                    if df is not None and not df.empty:
                        rows = self._df_to_rows(df)
                        if rows:
                            self.cache.set_cached_historical(sym, period, rows)
                            result[sym] = rows
                            ok_count += 1
                logger.info(
                    f"BATCH_HISTORICAL_TIER1: {ok_count}/{len(missing)} symbols OK "
                    f"({elapsed:.1f}s)"
                )
            except Exception as e:
                elapsed = time.time() - t0
                logger.warning(
                    f"BATCH_HISTORICAL_TIER1 FAILED: {elapsed:.1f}s error={e}"
                )

        still_missing = [s for s in missing if s not in result]

        # ── TIER 2: Smaller batch groups (groups of 5) ──────────
        if still_missing and breaker.allow_request():
            batch_size = 5
            for i in range(0, len(still_missing), batch_size):
                batch = still_missing[i:i + batch_size]
                t0 = time.time()
                try:
                    frames = await self.provider.get_batch_historical(batch, period=period)
                    elapsed = time.time() - t0
                    ok_count = 0
                    for sym, df in frames.items():
                        if sym in result:
                            continue
                        if df is not None and not df.empty:
                            rows = self._df_to_rows(df)
                            if rows:
                                self.cache.set_cached_historical(sym, period, rows)
                                result[sym] = rows
                                ok_count += 1
                    logger.info(
                        f"BATCH_HISTORICAL_TIER2 batch {i//batch_size + 1}: "
                        f"{ok_count}/{len(batch)} symbols OK ({elapsed:.1f}s)"
                    )
                except Exception as e:
                    elapsed = time.time() - t0
                    logger.warning(
                        f"BATCH_HISTORICAL_TIER2 FAILED: batch {i//batch_size + 1} "
                        f"({elapsed:.1f}s) error={e}"
                    )

        still_missing = [s for s in missing if s not in result]

        # ── TIER 3: Individual per-symbol fallback ───────────────
        if still_missing and breaker.allow_request():
            logger.info(
                f"BATCH_HISTORICAL_TIER3: {len(still_missing)} symbols "
                f"need individual fetch"
            )
            semaphore = asyncio.Semaphore(_MAX_FALLBACK_CONCURRENCY)

            async def _fallback_one(sym: str):
                async with semaphore:
                    try:
                        await asyncio.sleep(0.3)
                        rows = await self.get_historical_prices(sym, period=period)
                        if rows:
                            logger.info(f"TIER3_OK: {sym} — {len(rows)} rows")
                        else:
                            logger.warning(f"TIER3_EMPTY: {sym} — no rows returned")
                        return sym, rows
                    except Exception as e:
                        logger.warning(f"TIER3_FAIL: {sym} — {e}")
                        return sym, []

            fallback = await asyncio.gather(
                *[_fallback_one(s) for s in still_missing],
                return_exceptions=True,
            )
            for item in fallback:
                if isinstance(item, tuple):
                    sym, rows = item
                    if rows:
                        result[sym] = rows

        still_missing = [s for s in missing if s not in result]

        # ── TIER 4: Stale DB cache ──────────────────────────────
        if still_missing:
            stale = self._serve_stale_historical(still_missing, period)
            result.update(stale)
            if stale:
                logger.info(f"BATCH_HISTORICAL_TIER4: served stale cache for {len(stale)} symbols")

        # Final summary
        final_with_data = sum(1 for s in missing if s in result)
        final_missing = [s for s in missing if s not in result]
        logger.info(
            f"BATCH_HISTORICAL_DONE: {final_with_data}/{len(missing)} symbols have data, "
            f"{len(final_missing)} still missing"
            f"{f' missing={final_missing}' if final_missing else ''}"
        )

        return result

    def _serve_stale_historical(self, symbols: List[str], period: str) -> Dict[str, List[Dict[str, Any]]]:
        """Serve stale-but-valid cached historical data (up to 7 days old)."""
        STALE_TTL = 86400 * 7  # 7 days
        stale = {}
        for sym in symbols:
            try:
                from app.models.cache import HistoricalPriceCache
                cache = self.db.query(HistoricalPriceCache).filter(
                    HistoricalPriceCache.symbol == sym,
                    HistoricalPriceCache.period == period,
                ).first()
                if cache and cache.data:
                    age_s = (datetime.utcnow() - cache.cached_at).total_seconds()
                    if age_s < STALE_TTL:
                        stale[sym] = cache.data
                        logger.info(f"Stale cache served for {sym}: age={age_s/3600:.1f}h")
            except Exception:
                pass
        return stale

    async def get_stock_news(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get stock news with caching, in-flight dedup, and entity-resolution filtering."""
        from app.services.news_relevance_service import get_news_relevance_service
        from app.utils.stock_directory import lookup_company_name
        from app.utils.resilience import get_circuit_breaker

        canonical = self._normalize_symbol(symbol)
        cached = self.cache.get_cached_news(canonical, limit)
        if cached:
            return cached

        # CRITICAL: Check circuit breaker before any Yahoo news call
        breaker = get_circuit_breaker("yahoo")
        if not breaker.allow_request():
            logger.debug(f"News skipped for {canonical}: circuit breaker open")
            return []

        async def _fetch():
            articles = await self.provider.get_stock_news(canonical, limit)

            # Evidence-based filtering
            company_name = lookup_company_name(canonical)
            try:
                cached_info = self.cache.get_cached_stock_info_any_age(canonical)
                if not company_name and cached_info and cached_info.get("name"):
                    company_name = cached_info["name"]
            except Exception:
                pass

            relevance = get_news_relevance_service()
            articles = relevance.attach_relevance(
                articles, canonical, company_name, min_threshold=0.50
            )

            if articles:
                from app.engines.sentiment import SentimentEngine
                sentiment_engine = SentimentEngine()
                for article in articles:
                    sentiment = sentiment_engine.analyze_text(article.get("title", ""))
                    article["sentiment_score"] = sentiment["score"]
                    article["sentiment_label"] = sentiment["label"]
                    article["impact"] = sentiment.get("impact", "low")

                self.cache.set_cached_news(articles, canonical)

            return articles

        return await self._dedup(f"news:{canonical}", _fetch)

    async def search_stocks(self, query: str) -> List[Dict[str, Any]]:
        """Search for stocks by symbol or name."""
        canonical = self._normalize_symbol(query)
        return await self.provider.search_symbol(canonical)

    async def get_earnings_data(self, symbol: str) -> Dict[str, Any]:
        """Get earnings history and calendar (cached 30 min in-memory)."""
        canonical = self._normalize_symbol(symbol)
        now = time.time()
        cached = _earnings_cache.get(canonical)
        if cached and (now - cached[1]) < _EARNINGS_TTL:
            return cached[0]
        data = await self.provider.get_earnings(canonical)
        if data:
            _earnings_cache[canonical] = (data, now)
        return data or {}

    async def get_financials(self, symbol: str) -> Dict[str, Any]:
        """Get financial statements with caching."""
        canonical = self._normalize_symbol(symbol)
        cached = self.cache.get_cached_fundamentals(canonical)
        if cached:
            return cached

        data = await self.provider.get_financials(canonical)
        if data:
            info = await self.get_stock_info(canonical)
            full_data = {
                "data": info,
                "financials": data.get("income_statement"),
                "balance_sheet": data.get("balance_sheet"),
                "cash_flow": data.get("cash_flow"),
            }
            self.cache.set_cached_fundamentals(canonical, full_data)
            return full_data
        return {}
