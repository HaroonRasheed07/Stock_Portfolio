"""
Cache manager for efficient data retrieval with TTL-based invalidation.
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.stock_cache import (
    StockInfo, PriceCache, FundamentalCache,
    HistoricalPriceCache, NewsCache, AnalysisCache,
)

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages data caching with TTL-based invalidation."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _is_fresh(self, cached_at: Optional[datetime], ttl_seconds: int) -> bool:
        """Check if cached data is still fresh."""
        if not cached_at:
            return False
        age = (datetime.utcnow() - cached_at).total_seconds()
        return age < ttl_seconds

    # ── Price Cache ──────────────────────────────────────

    def get_cached_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached price if fresh."""
        cache = self.db.query(PriceCache).filter(PriceCache.symbol == symbol).first()
        if cache and self._is_fresh(cache.cached_at, self.settings.PRICE_CACHE_TTL):
            return {
                "symbol": cache.symbol,
                "price": cache.price,
                "previous_close": cache.previous_close,
                "open": cache.open_price,
                "day_high": cache.day_high,
                "day_low": cache.day_low,
                "volume": cache.volume,
                "avg_volume": cache.avg_volume,
                "fifty_two_week_high": cache.fifty_two_week_high,
                "fifty_two_week_low": cache.fifty_two_week_low,
                "change": cache.change,
                "change_pct": cache.change_pct,
                "cached_at": cache.cached_at,
            }
        return None

    def get_cached_price_any_age(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached price regardless of age (for display-only contexts like watchlist)."""
        cache = self.db.query(PriceCache).filter(PriceCache.symbol == symbol).first()
        if cache and cache.price is not None:
            return {
                "symbol": cache.symbol,
                "price": cache.price,
                "previous_close": cache.previous_close,
                "change": cache.change,
                "change_pct": cache.change_pct,
                "cached_at": cache.cached_at,
            }
        return None

    def set_cached_price(self, symbol: str, data: Dict[str, Any]):
        """Store or update price cache."""
        # NEVER cache null/None prices — they violate NOT NULL and corrupt the cache
        if not data.get("price"):
            return
        cache = self.db.query(PriceCache).filter(PriceCache.symbol == symbol).first()
        if not cache:
            cache = PriceCache(symbol=symbol)
            self.db.add(cache)

        cache.price = data.get("price")
        cache.previous_close = data.get("previous_close")
        cache.open_price = data.get("open")
        cache.day_high = data.get("day_high")
        cache.day_low = data.get("day_low")
        cache.volume = data.get("volume")
        cache.avg_volume = data.get("avg_volume")
        cache.fifty_two_week_high = data.get("fifty_two_week_high")
        cache.fifty_two_week_low = data.get("fifty_two_week_low")
        cache.change = data.get("change")
        cache.change_pct = data.get("change_pct")
        cache.cached_at = datetime.utcnow()
        self.db.commit()

    def get_cached_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached stock info if fresh."""
        cache = self.db.query(StockInfo).filter(StockInfo.symbol == symbol).first()
        if cache and self._is_fresh(cache.cached_at, self.settings.STOCK_INFO_CACHE_TTL):
            res = {
                "symbol": cache.symbol,
                "name": cache.name,
                "sector": cache.sector,
                "industry": cache.industry,
                "market_cap": cache.market_cap,
                "asset_type": cache.asset_type,
                "exchange": cache.exchange,
                "description": cache.description,
                "website": cache.website,
                "employees": cache.employees,
                "country": cache.country,
                "cached_at": cache.cached_at,
            }
            if cache.extra_data and isinstance(cache.extra_data, dict):
                res.update(cache.extra_data)
            return res
        return None

    def get_cached_stock_info_any_age(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached stock info regardless of TTL (for names/sector fallback)."""
        cache = self.db.query(StockInfo).filter(StockInfo.symbol == symbol).first()
        if not cache:
            return None
        res = {
            "symbol": cache.symbol,
            "name": cache.name,
            "sector": cache.sector,
            "industry": cache.industry,
            "market_cap": cache.market_cap,
            "asset_type": cache.asset_type,
        }
        if cache.extra_data and isinstance(cache.extra_data, dict):
            res.update(cache.extra_data)
        return res

    def set_cached_stock_info(self, symbol: str, data: Dict[str, Any]):
        """Store or update stock info cache."""
        cache = self.db.query(StockInfo).filter(StockInfo.symbol == symbol).first()
        if not cache:
            cache = StockInfo(symbol=symbol)
            self.db.add(cache)

        cache.name = data.get("name")
        cache.sector = data.get("sector")
        cache.industry = data.get("industry")
        cache.market_cap = data.get("market_cap")
        cache.asset_type = data.get("asset_type")
        cache.exchange = data.get("exchange")
        cache.description = data.get("description")
        cache.website = data.get("website")
        cache.employees = data.get("employees")
        cache.country = data.get("country")
        cache.extra_data = {
            k: v for k, v in data.items()
            if k not in ("symbol", "name", "sector", "industry", "market_cap",
                         "asset_type", "exchange", "description", "website",
                         "employees", "country", "error")
        }
        cache.cached_at = datetime.utcnow()
        self.db.commit()

    # ── Fundamental Cache ────────────────────────────────

    def get_cached_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached fundamental data if fresh."""
        cache = self.db.query(FundamentalCache).filter(
            FundamentalCache.symbol == symbol
        ).first()
        if cache and self._is_fresh(cache.cached_at, self.settings.FUNDAMENTALS_CACHE_TTL):
            return {
                "data": cache.data,
                "financials": cache.financials,
                "balance_sheet": cache.balance_sheet,
                "cash_flow": cache.cash_flow,
                "cached_at": cache.cached_at,
            }
        return None

    def set_cached_fundamentals(self, symbol: str, data: Dict[str, Any]):
        """Store or update fundamentals cache."""
        cache = self.db.query(FundamentalCache).filter(
            FundamentalCache.symbol == symbol
        ).first()
        if not cache:
            cache = FundamentalCache(symbol=symbol)
            self.db.add(cache)

        cache.data = data.get("data")
        cache.financials = data.get("financials")
        cache.balance_sheet = data.get("balance_sheet")
        cache.cash_flow = data.get("cash_flow")
        cache.cached_at = datetime.utcnow()
        self.db.commit()

    # ── Historical Price Cache ───────────────────────────

    def get_cached_historical(self, symbol: str, period: str) -> Optional[Any]:
        """Get cached historical price data if fresh."""
        cache = self.db.query(HistoricalPriceCache).filter(
            HistoricalPriceCache.symbol == symbol,
            HistoricalPriceCache.period == period,
        ).first()
        ttl = self.settings.PRICE_CACHE_TTL * 12  # 1 hour for historical
        if cache and self._is_fresh(cache.cached_at, ttl):
            return cache.data
        return None

    def set_cached_historical(self, symbol: str, period: str, data: Any):
        """Store or update historical price cache."""
        cache = self.db.query(HistoricalPriceCache).filter(
            HistoricalPriceCache.symbol == symbol,
            HistoricalPriceCache.period == period,
        ).first()
        if not cache:
            cache = HistoricalPriceCache(symbol=symbol, period=period)
            self.db.add(cache)

        cache.data = data
        cache.cached_at = datetime.utcnow()
        self.db.commit()

    # ── Analysis Cache ───────────────────────────────────

    def get_cached_analysis(self, symbol: str, analysis_type: str) -> Optional[Dict[str, Any]]:
        """Get cached analysis result if fresh."""
        cache = self.db.query(AnalysisCache).filter(
            AnalysisCache.symbol == symbol,
            AnalysisCache.analysis_type == analysis_type,
        ).first()
        if cache and self._is_fresh(cache.cached_at, self.settings.ANALYSIS_CACHE_TTL):
            return cache.result
        return None

    def set_cached_analysis(self, symbol: str, analysis_type: str, result: Dict[str, Any]):
        """Store or update analysis cache."""
        cache = self.db.query(AnalysisCache).filter(
            AnalysisCache.symbol == symbol,
            AnalysisCache.analysis_type == analysis_type,
        ).first()
        if not cache:
            cache = AnalysisCache(symbol=symbol, analysis_type=analysis_type)
            self.db.add(cache)

        cache.result = result
        cache.cached_at = datetime.utcnow()
        self.db.commit()

    # ── News Cache ───────────────────────────────────────

    def get_cached_news(self, symbol: Optional[str] = None, limit: int = 20) -> Optional[list]:
        """Get cached news if fresh."""
        query = self.db.query(NewsCache)
        if symbol:
            query = query.filter(NewsCache.symbol == symbol)
        # Check most recent article's cache time
        latest = query.order_by(NewsCache.cached_at.desc()).first()
        if not latest or not self._is_fresh(latest.cached_at, self.settings.NEWS_CACHE_TTL):
            return None

        articles = query.order_by(NewsCache.published_at.desc()).limit(limit).all()
        return [
            {
                "title": a.title,
                "summary": a.summary,
                "source": a.source,
                "url": a.url,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "symbol": a.symbol,
                "sentiment_score": a.sentiment_score,
                "sentiment_label": a.sentiment_label,
                "impact": a.impact,
                "category": a.category,
            }
            for a in articles
        ]

    def set_cached_news(self, articles: list, symbol: Optional[str] = None):
        """Store news articles in cache."""
        # Clear old news for this symbol
        query = self.db.query(NewsCache)
        if symbol:
            query = query.filter(NewsCache.symbol == symbol)
        query.delete()

        for article in articles:
            pub_at = article.get("published_at")
            if isinstance(pub_at, str):
                try:
                    pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
                except Exception:
                    pub_at = None

            news = NewsCache(
                symbol=symbol or article.get("symbol"),
                title=article.get("title", ""),
                summary=article.get("summary"),
                source=article.get("source"),
                url=article.get("url"),
                published_at=pub_at,
                sentiment_score=article.get("sentiment_score"),
                sentiment_label=article.get("sentiment_label"),
                impact=article.get("impact"),
                category=article.get("category"),
                cached_at=datetime.utcnow(),
            )
            self.db.add(news)

        self.db.commit()

    # ── Bulk Operations ──────────────────────────────────

    def clear_all_caches(self):
        """Clear all cached data (for manual refresh)."""
        self.db.query(PriceCache).delete()
        self.db.query(FundamentalCache).delete()
        self.db.query(HistoricalPriceCache).delete()
        self.db.query(NewsCache).delete()
        self.db.query(AnalysisCache).delete()
        self.db.commit()
        logger.info("All caches cleared.")

    def clear_symbol_cache(self, symbol: str):
        """Clear all cached data for a specific symbol."""
        self.db.query(PriceCache).filter(PriceCache.symbol == symbol).delete()
        self.db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).delete()
        self.db.query(HistoricalPriceCache).filter(HistoricalPriceCache.symbol == symbol).delete()
        self.db.query(NewsCache).filter(NewsCache.symbol == symbol).delete()
        self.db.query(AnalysisCache).filter(AnalysisCache.symbol == symbol).delete()
        self.db.commit()
