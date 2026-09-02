"""
Catalyst Service — orchestrates news ingestion, catalyst detection, alert generation,
and portfolio/watchlist relevance across multiple providers.
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session

from app.engines.catalyst import CatalystEngine
from app.engines.sentiment import SentimentEngine
from app.models.catalyst import CatalystEvent, CatalystAlert, CatalystWatchItem, NewsDedup
from app.models.holding import Holding
from app.models.watchlist import WatchlistItem
from app.models.portfolio import Portfolio
from app.providers.yfinance_provider import get_yfinance_provider
from app.providers.finnhub_provider import get_finnhub_provider
from app.providers.rss_provider import get_rss_provider
from app.services.news_relevance_service import get_news_relevance_service
from app.utils.stock_directory import lookup_company_name

logger = logging.getLogger(__name__)


class CatalystService:
    """
    Orchestrates news ingestion, catalyst classification, alert generation,
    and portfolio relevance tracking.
    """

    def __init__(self, db: Session):
        self.db = db
        self.catalyst_engine = CatalystEngine()
        self.sentiment_engine = SentimentEngine()
        self.yfinance = get_yfinance_provider()
        self.finnhub = get_finnhub_provider()
        self.rss = get_rss_provider()
        self.relevance = get_news_relevance_service()

    def _get_portfolio_symbols(self) -> Set[str]:
        """Get all symbols currently in the portfolio."""
        holdings = self.db.query(Holding).all()
        return {h.symbol for h in holdings}

    def _get_watchlist_symbols(self) -> Set[str]:
        """Get all symbols on the watchlist."""
        items = self.db.query(WatchlistItem).all()
        return {item.symbol for item in items}

    def _is_duplicate(self, content_hash: str) -> bool:
        """Check if an article has already been seen."""
        if not content_hash:
            return False
        existing = self.db.query(NewsDedup).filter(
            NewsDedup.content_hash == content_hash
        ).first()
        return existing is not None

    def _mark_seen(self, content_hash: str, symbol: str = None, source: str = None):
        """Mark an article as seen for dedup."""
        if not content_hash:
            return
        existing = self.db.query(NewsDedup).filter(
            NewsDedup.content_hash == content_hash
        ).first()
        if not existing:
            dedup = NewsDedup(
                content_hash=content_hash,
                symbol=symbol,
                source=source,
            )
            self.db.add(dedup)
            self.db.commit()

    def _cleanup_old_dedup(self, days: int = 7):
        """Remove dedup entries older than N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        self.db.query(NewsDedup).filter(NewsDedup.first_seen < cutoff).delete()
        self.db.commit()

    def _company_name_for(self, symbol: str) -> Optional[str]:
        """Best-known company name for a symbol (DB cache first, then directory)."""
        try:
            from app.models.stock_cache import StockInfo
            info = self.db.query(StockInfo).filter(StockInfo.symbol == symbol.upper()).first()
            if info and info.name:
                return info.name
        except Exception:
            pass
        return lookup_company_name(symbol)

    async def _fetch_news_from_providers(
        self, symbol: str = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Fetch news from all available providers with fallback."""
        all_articles = []

        # 1. yfinance (always available, no API key)
        try:
            if symbol:
                articles = await self.yfinance.get_stock_news(symbol, limit=limit)
            else:
                articles = await self.yfinance.get_market_news(limit=limit)
            all_articles.extend(articles)
        except Exception as e:
            logger.warning(f"yfinance news fetch failed: {e}")

        # 2. Finnhub (if configured)
        if self.finnhub.is_configured:
            try:
                if symbol:
                    articles = await self.finnhub.get_stock_news(symbol, limit=limit)
                else:
                    articles = await self.finnhub.get_market_news(limit=limit)
                all_articles.extend(articles)
            except Exception as e:
                logger.warning(f"Finnhub news fetch failed: {e}")

        # 3. RSS feeds (always available, no API key)
        try:
            if symbol:
                articles = await self.rss.get_stock_news(symbol, limit=limit)
            else:
                articles = await self.rss.get_market_news(limit=limit)
            all_articles.extend(articles)
        except Exception as e:
            logger.warning(f"RSS news fetch failed: {e}")

        return all_articles

    def _save_catalyst_event(self, catalyst: Dict[str, Any]) -> CatalystEvent:
        """Save a catalyst event to the database."""
        # Reject events with no symbol — the DB column is NOT NULL.
        # Market-wide articles without entity resolution must not reach the table.
        raw_symbol = catalyst.get("symbol")
        if not raw_symbol or not str(raw_symbol).strip():
            raise ValueError("Cannot save catalyst event without a symbol")

        pub_at = catalyst.get("published_at")
        if isinstance(pub_at, str):
            try:
                pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
            except Exception:
                pub_at = None
        # Do NOT fabricate timestamps — let published_at be None
        # Frontend will display "Date unavailable" for missing timestamps

        event = CatalystEvent(
            symbol=str(raw_symbol).strip().upper(),
            company=catalyst.get("company", ""),
            headline=catalyst.get("headline", ""),
            summary=catalyst.get("summary", ""),
            source=catalyst.get("source", ""),
            url=catalyst.get("url", ""),
            published_at=pub_at,
            catalyst_type=catalyst.get("catalyst_type", ""),
            category=catalyst.get("category", ""),
            impact_level=catalyst.get("impact_level", "LOW"),
            sentiment_score=catalyst.get("sentiment_score"),
            sentiment_label=catalyst.get("sentiment_label", "neutral"),
            relevance_score=catalyst.get("relevance_score"),
            confidence=catalyst.get("confidence"),
            potential_impact=catalyst.get("potential_impact", ""),
            affects_holding=catalyst.get("affects_holding", 0),
            affects_watchlist=catalyst.get("affects_watchlist", 0),
            long_term_view=catalyst.get("long_term_view", ""),
            short_term_view=catalyst.get("short_term_view", ""),
            content_hash=catalyst.get("content_hash", ""),
            provider=catalyst.get("provider", ""),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def _generate_catalyst_alert(
        self, event: CatalystEvent, catalyst: Dict[str, Any]
    ) -> Optional[CatalystAlert]:
        """Generate an alert for a significant catalyst event."""
        # Determine alert type based on context
        alert_type = None
        title = ""
        message = ""

        if event.impact_level == "CRITICAL":
            alert_type = "critical_news"
            title = f"CRITICAL: {event.catalyst_type.replace('_', ' ').title()}"
            message = f"{event.headline}. {event.potential_impact or ''}"
        elif event.impact_level == "HIGH":
            if event.affects_holding:
                alert_type = "portfolio_holding_news"
                title = f"HIGH IMPACT - Portfolio Holding: {event.symbol}"
                message = f"{event.headline}. This affects a holding in your portfolio."
            elif event.affects_watchlist:
                alert_type = "watchlist_news"
                title = f"HIGH IMPACT - Watchlist: {event.symbol}"
                message = f"{event.headline}. This affects a stock on your watchlist."
            else:
                alert_type = "high_impact_catalyst"
                title = f"High Impact Catalyst: {event.symbol}"
                message = f"{event.headline}"
        elif event.sentiment_label == "positive" and event.impact_level == "MEDIUM":
            alert_type = "positive_catalyst"
            title = f"Positive Catalyst: {event.symbol}"
            message = f"{event.headline}"
        elif event.sentiment_label == "negative" and event.impact_level in ("HIGH", "MEDIUM"):
            alert_type = "negative_catalyst"
            title = f"Negative Catalyst: {event.symbol}"
            message = f"{event.headline}"
        else:
            return None  # Don't generate alert for LOW or neutral MEDIUM events

        if not alert_type:
            return None

        alert = CatalystAlert(
            catalyst_event_id=event.id,
            symbol=event.symbol,
            alert_type=alert_type,
            title=title,
            message=message,
            impact_level=event.impact_level,
            price_reaction_pct=event.price_reaction_pct,
            volume_ratio=event.volume_ratio,
            catalyst_type=event.catalyst_type,
            sentiment_label=event.sentiment_label,
        )
        self.db.add(alert)
        self.db.commit()
        return alert

    def _update_catalyst_watch(self, symbol: str, catalysts: List[Dict[str, Any]]):
        """Update the catalyst watch item for a symbol."""
        watch = self.db.query(CatalystWatchItem).filter(
            CatalystWatchItem.symbol == symbol
        ).first()

        if not watch:
            watch = CatalystWatchItem(symbol=symbol)
            self.db.add(watch)

        now = datetime.utcnow()
        count_24h = 0
        count_7d = 0
        high_impact_count = 0
        sentiments = []

        for cat in catalysts:
            pub = cat.get("published_at")
            if not pub:
                continue
            if isinstance(pub, str):
                try:
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00").replace("+00:00", ""))
                except Exception:
                    continue

            age = (now - pub).total_seconds()
            if age < 86400:
                count_24h += 1
            if age < 604800:
                count_7d += 1
            if cat.get("impact_level") in ("HIGH", "CRITICAL"):
                high_impact_count += 1
            if cat.get("sentiment_score") is not None:
                sentiments.append(cat["sentiment_score"])

        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else None

        # Determine attention trend
        prev_7d = watch.news_frequency_7d or 0
        if count_7d > prev_7d * 1.5 and prev_7d > 0:
            attention_trend = "increasing"
        elif count_7d > 0 and prev_7d == 0:
            attention_trend = "increasing"
        elif count_7d < prev_7d * 0.5 and prev_7d > 0:
            attention_trend = "decreasing"
        else:
            attention_trend = "stable"

        # Generate early signal
        early_signal = None
        if attention_trend == "increasing" and high_impact_count > 0:
            early_signal = "Potential catalyst developing - attention increasing"
        elif count_24h >= 3:
            early_signal = "Unusual activity detected - high news frequency"
        elif high_impact_count >= 2:
            early_signal = "Multiple high-impact events detected this week"

        watch.news_frequency_24h = count_24h
        watch.news_frequency_7d = count_7d
        watch.avg_sentiment_24h = avg_sentiment
        watch.avg_sentiment_7d = avg_sentiment  # simplified
        watch.high_impact_count_7d = high_impact_count
        watch.attention_trend = attention_trend
        watch.early_signal = early_signal
        watch.early_catalyst_watch = 1 if early_signal else 0
        watch.is_holding = 1 if symbol in self._get_portfolio_symbols() else 0
        watch.is_watchlist = 1 if symbol in self._get_watchlist_symbols() else 0
        watch.last_checked = now
        watch.updated_at = now

        self.db.commit()

    # ── Public API ───────────────────────────────────────

    async def scan_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Scan a single symbol for catalysts.
        Fetches news, classifies, stores, and generates alerts.

        ENTITY RESOLUTION: every article is verified against textual evidence
        (ticker reference or company-name reference) before being associated
        with the symbol. Provider-asserted symbols alone are NOT trusted.
        """
        from app.utils.ticker import normalize_ticker
        symbol = normalize_ticker(symbol)
        portfolio_symbols = self._get_portfolio_symbols()
        watchlist_symbols = self._get_watchlist_symbols()

        # Register company names so name-based evidence works
        company_name = self._company_name_for(symbol)
        self.relevance.register_company(symbol, company_name)

        # Fetch news
        articles = await self._fetch_news_from_providers(symbol=symbol, limit=20)

        # Evidence-based relevance filtering — THE Walmart/O fix.
        # Articles without real references to this company are dropped here.
        evidenced_articles = self.relevance.attach_relevance(
            articles, symbol, company_name, min_threshold=0.70
        )

        # Classify only evidenced articles as catalysts for this symbol
        catalysts = self.catalyst_engine.classify_articles(evidenced_articles)

        # Deduplicate
        new_catalysts = []
        for cat in catalysts:
            if not self._is_duplicate(cat.get("content_hash", "")):
                # affects_holding/watchlist ONLY with evidence + membership
                cat["affects_holding"] = 1 if symbol in portfolio_symbols else 0
                cat["affects_watchlist"] = 1 if symbol in watchlist_symbols else 0
                cat["company"] = cat.get("company") or company_name or ""
                new_catalysts.append(cat)

        # Save and generate alerts
        saved_events = []
        alerts_generated = 0
        for cat in new_catalysts:
            self._mark_seen(cat.get("content_hash", ""), symbol, cat.get("provider"))
            event = self._save_catalyst_event(cat)
            cat["id"] = event.id
            saved_events.append(cat)

            # Generate alert for significant events
            if cat["impact_level"] in ("HIGH", "CRITICAL"):
                alert = self._generate_catalyst_alert(event, cat)
                if alert:
                    alerts_generated += 1

        # Update catalyst watch
        self._update_catalyst_watch(symbol, catalysts)

        return {
            "symbol": symbol,
            "articles_fetched": len(articles),
            "catalysts_detected": len(catalysts),
            "new_catalysts": len(saved_events),
            "alerts_generated": alerts_generated,
            "catalysts": saved_events,
        }

    async def scan_portfolio(self) -> Dict[str, Any]:
        """Scan all portfolio holdings for catalysts."""
        portfolio_symbols = self._get_portfolio_symbols()
        results = {}

        for symbol in portfolio_symbols:
            try:
                result = await self.scan_symbol(symbol)
                results[symbol] = result
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                results[symbol] = {"error": str(e)}

        return {
            "symbols_scanned": len(portfolio_symbols),
            "results": results,
            "scan_time": datetime.utcnow().isoformat(),
        }

    async def scan_watchlist(self) -> Dict[str, Any]:
        """Scan all watchlist symbols for catalysts."""
        watchlist_symbols = self._get_watchlist_symbols()
        results = {}

        for symbol in watchlist_symbols:
            try:
                result = await self.scan_symbol(symbol)
                results[symbol] = result
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                results[symbol] = {"error": str(e)}

        return {
            "symbols_scanned": len(watchlist_symbols),
            "results": results,
            "scan_time": datetime.utcnow().isoformat(),
        }

    async def scan_market_news(self) -> Dict[str, Any]:
        """Scan general market news for catalysts (entity-resolved)."""
        try:
            raw_articles = await self._fetch_news_from_providers(symbol=None, limit=30)
        except Exception as e:
            logger.error(f"Failed to fetch market news: {e}")
            return {"articles_fetched": 0, "catalysts_detected": 0,
                    "actionable_catalysts": 0, "catalysts": []}

        if not raw_articles:
            return {"articles_fetched": 0, "catalysts_detected": 0,
                    "actionable_catalysts": 0, "catalysts": []}

        # Strip provider-asserted symbols (e.g. the SPY proxy) — they are NOT
        # evidence. Re-associate ONLY via textual evidence against our universe.
        for art in raw_articles:
            art["symbol"] = None
            art["company"] = ""

        universe = {s: {"name": self._company_name_for(s)}
                    for s in (self._get_portfolio_symbols() | self._get_watchlist_symbols())}
        resolved = self.relevance.resolve_universe(raw_articles, universe)

        # Company-specific evidenced articles + unassigned market-wide ones
        articles = []
        for sym, arts in resolved.items():
            if sym == "_unassigned":
                articles.extend(arts)
            else:
                articles.extend(arts)

        # Classify without blind symbol association
        catalysts = self.catalyst_engine.classify_articles(articles)

        # Filter to only significant
        portfolio_symbols = self._get_portfolio_symbols()
        watchlist_symbols = self._get_watchlist_symbols()
        filtered = self.catalyst_engine.filter_actionable(
            catalysts, portfolio_symbols, watchlist_symbols, min_impact="MEDIUM"
        )

        saved = []
        for cat in filtered:
            # Skip market-wide articles that were not entity-resolved to a symbol
            if not cat.get("symbol"):
                continue
            try:
                if not self._is_duplicate(cat.get("content_hash", "")):
                    self._mark_seen(cat.get("content_hash", ""), cat.get("symbol"), cat.get("provider"))
                    event = self._save_catalyst_event(cat)
                    cat["id"] = event.id
                    saved.append(cat)
            except Exception as e:
                logger.error(f"Error saving catalyst event: {e}")
                continue

        return {
            "articles_fetched": len(raw_articles),
            "evidenced_associations": sum(
                len(v) for k, v in resolved.items() if k != "_unassigned"
            ),
            "market_wide": len(resolved.get("_unassigned", [])),
            "catalysts_detected": len(catalysts),
            "actionable_catalysts": len(saved),
            "catalysts": saved,
        }

    def get_catalyst_events(
        self,
        symbol: Optional[str] = None,
        impact_level: Optional[str] = None,
        catalyst_type: Optional[str] = None,
        scope: Optional[str] = None,
        limit: int = 50,
        hours_back: int = 72,
    ) -> List[Dict[str, Any]]:
        """Get stored catalyst events with optional filters."""
        query = self.db.query(CatalystEvent)

        if symbol:
            query = query.filter(CatalystEvent.symbol == symbol.upper())
        if impact_level:
            query = query.filter(CatalystEvent.impact_level == impact_level.upper())
        if catalyst_type:
            query = query.filter(CatalystEvent.catalyst_type == catalyst_type)
        if scope == "portfolio":
            query = query.filter(CatalystEvent.affects_holding == 1)
        elif scope == "watchlist":
            query = query.filter(CatalystEvent.affects_watchlist == 1)

        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        query = query.filter(CatalystEvent.retrieved_at >= cutoff)

        events = query.order_by(CatalystEvent.published_at.desc()).limit(limit).all()

        portfolio_symbols = self._get_portfolio_symbols()
        watchlist_symbols = self._get_watchlist_symbols()

        result = []
        for e in events:
            sym = (e.symbol or "").upper()
            if e.affects_holding:
                relevance_label = "DIRECT HOLDING"
                relevance_reason = f"Direct company news affecting your current {sym} position."
            elif e.affects_watchlist or sym in watchlist_symbols:
                relevance_label = "WATCHLIST"
                relevance_reason = f"{sym} is on your watchlist."
            elif sym in portfolio_symbols:
                relevance_label = "PORTFOLIO HOLDING"
                relevance_reason = f"Relates to {sym}, a company you hold, though the article may discuss broader topics."
            else:
                relevance_label = "MARKET-WIDE"
                relevance_reason = f"Market development involving {sym}. This is not a current holding."

            result.append({
                "id": e.id,
                "symbol": e.symbol,
                "company": e.company,
                "headline": e.headline,
                "summary": e.summary,
                "source": e.source,
                "url": e.url,
                "published_at": e.published_at.isoformat() if e.published_at else None,
                "retrieved_at": e.retrieved_at.isoformat() if e.retrieved_at else None,
                "catalyst_type": e.catalyst_type,
                "category": e.category,
                "impact_level": e.impact_level,
                "sentiment_score": e.sentiment_score,
                "sentiment_label": e.sentiment_label,
                "relevance_score": e.relevance_score,
                "confidence": e.confidence,
                "potential_impact": e.potential_impact,
                "affects_holding": bool(e.affects_holding),
                "affects_watchlist": bool(e.affects_watchlist),
                "relevance_label": relevance_label,
                "relevance_reason": relevance_reason,
                "allocation_pct": e.allocation_pct,
                "price_reaction_pct": e.price_reaction_pct,
                "volume_ratio": e.volume_ratio,
                "long_term_view": e.long_term_view,
                "short_term_view": e.short_term_view,
                "provider": e.provider,
            })

        return result

    def get_catalyst_timeline(self, symbol: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Get catalyst timeline for a specific symbol."""
        events = self.db.query(CatalystEvent).filter(
            CatalystEvent.symbol == symbol.upper()
        ).order_by(CatalystEvent.published_at.desc()).limit(limit).all()

        timeline = []
        for e in events:
            timeline.append({
                "id": e.id,
                "date": e.published_at.isoformat() if e.published_at else None,
                "event": e.catalyst_type.replace("_", " ").title(),
                "headline": e.headline,
                "sentiment": e.sentiment_label,
                "sentiment_score": e.sentiment_score,
                "impact": e.impact_level,
                "source": e.source,
                "url": e.url,
                "price_reaction": e.price_reaction_pct,
                "volume_ratio": e.volume_ratio,
                "long_term_view": e.long_term_view,
                "short_term_view": e.short_term_view,
            })

        return timeline

    def get_catalyst_alerts(
        self, unread_only: bool = False, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get catalyst alerts with portfolio-relevance context."""
        query = self.db.query(CatalystAlert)
        if unread_only:
            query = query.filter(CatalystAlert.is_read == 0)

        alerts = query.order_by(CatalystAlert.created_at.desc()).limit(limit).all()

        portfolio_symbols = self._get_portfolio_symbols()
        watchlist_symbols = self._get_watchlist_symbols()

        return [
            {
                "id": a.id,
                "catalyst_event_id": a.catalyst_event_id,
                "symbol": a.symbol,
                "alert_type": a.alert_type,
                "title": a.title,
                "message": a.message,
                "impact_level": a.impact_level,
                "price_reaction_pct": a.price_reaction_pct,
                "volume_ratio": a.volume_ratio,
                "portfolio_exposure_pct": a.portfolio_exposure_pct,
                "catalyst_type": a.catalyst_type,
                "sentiment_label": a.sentiment_label,
                "is_holding": (a.symbol or "").upper() in portfolio_symbols,
                "is_watchlist": (a.symbol or "").upper() in watchlist_symbols,
                "relevance_reason": (
                    f"Affects your current {(a.symbol or '').upper()} position."
                    if (a.symbol or "").upper() in portfolio_symbols
                    else (
                        f"{(a.symbol or '').upper()} is on your watchlist."
                        if (a.symbol or "").upper() in watchlist_symbols
                        else f"Market event involving {(a.symbol or '').upper()} — not currently held."
                    )
                ),
                "is_read": bool(a.is_read),
                "is_dismissed": bool(a.is_dismissed),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ]

    def get_unread_alert_count(self) -> int:
        """Get count of unread catalyst alerts."""
        return self.db.query(CatalystAlert).filter(
            CatalystAlert.is_read == 0
        ).count()

    def mark_alert_read(self, alert_id: int):
        """Mark an alert as read."""
        alert = self.db.query(CatalystAlert).filter(CatalystAlert.id == alert_id).first()
        if alert:
            alert.is_read = 1
            self.db.commit()

    def mark_all_alerts_read(self):
        """Mark all alerts as read."""
        self.db.query(CatalystAlert).filter(
            CatalystAlert.is_read == 0
        ).update({"is_read": 1})
        self.db.commit()

    def dismiss_alert(self, alert_id: int):
        """Dismiss an alert."""
        alert = self.db.query(CatalystAlert).filter(CatalystAlert.id == alert_id).first()
        if alert:
            alert.is_dismissed = 1
            alert.is_read = 1
            self.db.commit()

    def get_catalyst_watch(self) -> List[Dict[str, Any]]:
        """Get all catalyst watch items (stocks with increasing attention)."""
        items = self.db.query(CatalystWatchItem).order_by(
            CatalystWatchItem.news_frequency_7d.desc(),
            CatalystWatchItem.high_impact_count_7d.desc(),
        ).all()

        return [
            {
                "id": w.id,
                "symbol": w.symbol,
                "company": w.company,
                "news_frequency_24h": w.news_frequency_24h,
                "news_frequency_7d": w.news_frequency_7d,
                "avg_sentiment_24h": w.avg_sentiment_24h,
                "high_impact_count_7d": w.high_impact_count_7d,
                "attention_trend": w.attention_trend,
                "early_signal": w.early_signal,
                "early_catalyst_watch": bool(w.early_catalyst_watch),
                "is_holding": bool(w.is_holding),
                "is_watchlist": bool(w.is_watchlist),
                "last_checked": w.last_checked.isoformat() if w.last_checked else None,
            }
            for w in items
        ]

    def get_catalyst_summary(self) -> Dict[str, Any]:
        """Get overall catalyst summary for dashboard."""
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        total_24h = self.db.query(CatalystEvent).filter(
            CatalystEvent.retrieved_at >= last_24h
        ).count()
        total_7d = self.db.query(CatalystEvent).filter(
            CatalystEvent.retrieved_at >= last_7d
        ).count()

        high_impact_24h = self.db.query(CatalystEvent).filter(
            CatalystEvent.retrieved_at >= last_24h,
            CatalystEvent.impact_level.in_(["HIGH", "CRITICAL"])
        ).count()

        critical_count = self.db.query(CatalystEvent).filter(
            CatalystEvent.retrieved_at >= last_7d,
            CatalystEvent.impact_level == "CRITICAL"
        ).count()

        high_count = self.db.query(CatalystEvent).filter(
            CatalystEvent.retrieved_at >= last_7d,
            CatalystEvent.impact_level == "HIGH"
        ).count()

        portfolio_catalysts = self.db.query(CatalystEvent).filter(
            CatalystEvent.retrieved_at >= last_24h,
            CatalystEvent.affects_holding == 1,
        ).count()

        unread_alerts = self.get_unread_alert_count()

        watch_items = self.db.query(CatalystWatchItem).filter(
            CatalystWatchItem.attention_trend == "increasing"
        ).count()

        symbols_tracked = self.db.query(CatalystEvent.symbol).distinct().count()

        recent_events_raw = self.db.query(CatalystEvent).order_by(
            CatalystEvent.retrieved_at.desc()
        ).limit(5).all()

        # Portfolio-relevant events (7d) with sentiment breakdown
        portfolio_events = self.db.query(CatalystEvent).filter(
            CatalystEvent.retrieved_at >= last_7d,
            CatalystEvent.affects_holding == 1,
        ).order_by(CatalystEvent.published_at.desc()).limit(20).all()

        positive = sum(1 for e in portfolio_events if (e.sentiment_label or "") == "positive")
        negative = sum(1 for e in portfolio_events if (e.sentiment_label or "") == "negative")
        neutral = len(portfolio_events) - positive - negative

        # Highest-impact recent event affecting the portfolio
        top_event = None
        priority = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        ranked = sorted(portfolio_events, key=lambda e: priority.get(e.impact_level or "LOW", 9))
        if ranked:
            e = ranked[0]
            top_event = {
                "symbol": e.symbol,
                "headline": e.headline,
                "impact_level": e.impact_level,
                "sentiment_label": e.sentiment_label,
                "catalyst_type": e.catalyst_type,
            }

        if negative > positive:
            portfolio_impact = "Negative news outweighs positive for your holdings"
        elif positive > negative:
            portfolio_impact = "Positive news outweighs negative for your holdings"
        elif positive == 0 and negative == 0:
            portfolio_impact = "No significant news detected for your holdings this week"
        else:
            portfolio_impact = "Mixed news flow — positives and negatives balance out"

        return {
            "catalysts_24h": total_24h,
            "catalysts_7d": total_7d,
            "total_events": total_7d,
            "high_impact_24h": high_impact_24h,
            "critical_count": critical_count,
            "high_count": high_count,
            "portfolio_catalysts_24h": portfolio_catalysts,
            "portfolio_catalysts_7d": len(portfolio_events),
            "portfolio_sentiment": {
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
            },
            "top_event": top_event,
            "portfolio_impact_summary": portfolio_impact,
            "unread_alerts": unread_alerts,
            "stocks_with_increasing_attention": watch_items,
            "symbols_tracked": symbols_tracked,
            "last_scan": now.isoformat(),
            "recent_events": [
                {
                    "symbol": e.symbol,
                    "title": e.headline,
                    "catalyst_type": e.catalyst_type,
                    "impact_level": e.impact_level,
                    "sentiment_score": e.sentiment_score,
                    "retrieved_at": e.retrieved_at.isoformat() if e.retrieved_at else None,
                }
                for e in recent_events_raw
            ],
        }

    def get_stock_sentiment_with_catalyst(self, symbol: str) -> Dict[str, Any]:
        """Get combined sentiment and catalyst data for a stock."""
        # Recent catalysts
        catalysts = self.get_catalyst_events(symbol=symbol, limit=10)

        # Aggregate sentiment
        scores = [c["sentiment_score"] for c in catalysts if c.get("sentiment_score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0

        if avg_score >= 0.15:
            overall = "Positive"
        elif avg_score <= -0.15:
            overall = "Negative"
        else:
            overall = "Neutral"

        return {
            "symbol": symbol,
            "overall_sentiment": overall,
            "avg_score": round(avg_score, 3),
            "catalyst_count": len(catalysts),
            "high_impact_count": sum(1 for c in catalysts if c.get("impact_level") in ("HIGH", "CRITICAL")),
            "catalysts": catalysts[:5],
        }

    def reclassify_events(self) -> Dict[str, Any]:
        """Reclassify all existing events using evidence-based entity resolution."""
        portfolio_symbols = self._get_portfolio_symbols()
        watchlist_symbols = self._get_watchlist_symbols()
        events = self.db.query(CatalystEvent).all()

        updated = 0
        for e in events:
            sym = (e.symbol or "").upper()
            if not sym:
                continue
            score = self.relevance.score_article(
                e.headline or "", e.summary or "", sym
            )
            has_evidence = score >= 0.70
            new_holding = 1 if (sym in portfolio_symbols and has_evidence) else 0
            new_watchlist = 1 if (sym in watchlist_symbols and has_evidence) else 0
            if e.affects_holding != new_holding or e.affects_watchlist != new_watchlist:
                e.affects_holding = new_holding
                e.affects_watchlist = new_watchlist
                updated += 1

        self.db.commit()
        return {"total_events": len(events), "updated": updated}
