"""
Finnhub news provider — free tier implementation.
Requires FINNHUB_API_KEY in environment. Falls back gracefully if not configured.
Uses httpx (already installed) instead of aiohttp.
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import httpx

from app.providers.base import NewsProvider
from app.config import get_settings

logger = logging.getLogger(__name__)


class FinnhubNewsProvider(NewsProvider):
    """
    Finnhub free-tier news provider.
    Free tier: 60 calls/minute, company news, market news, FDA calendar.
    """

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._last_request_time = 0
        self._min_interval = 1.1  # ~55 calls/min to stay under 60/min limit

    @property
    def api_key(self) -> Optional[str]:
        if self._api_key is None:
            settings = get_settings()
            self._api_key = settings.FINNHUB_API_KEY
        return self._api_key

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _throttle(self):
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    async def _get(self, endpoint: str, params: Dict[str, Any] = None) -> Any:
        """Make a throttled GET request to Finnhub using httpx."""
        if not self.is_configured:
            return None

        await self._throttle()
        url = f"{self.BASE_URL}{endpoint}"
        all_params = {"token": self.api_key}
        if params:
            all_params.update(params)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=all_params)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    logger.warning("Finnhub rate limit hit, skipping")
                    return None
                else:
                    logger.warning(f"Finnhub API error {resp.status_code}: {endpoint}")
                    return None
        except Exception as e:
            logger.error(f"Finnhub request failed for {endpoint}: {e}")
            return None

    async def get_stock_news(
        self, symbol: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get company news from Finnhub (free tier: last 7 days)."""
        if not self.is_configured:
            return []

        try:
            today = datetime.utcnow()
            week_ago = today - timedelta(days=7)

            data = await self._get(
                "/company-news",
                {
                    "symbol": symbol,
                    "from": week_ago.strftime("%Y-%m-%d"),
                    "to": today.strftime("%Y-%m-%d"),
                },
            )

            if not data or not isinstance(data, list):
                return []

            articles = []
            for item in data[:limit]:
                pub_ts = item.get("datetime")
                pub_date = None
                if pub_ts:
                    try:
                        pub_date = datetime.utcfromtimestamp(int(pub_ts))
                    except (ValueError, TypeError):
                        pub_date = None

                articles.append({
                    "title": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", "finnhub"),
                    "url": item.get("url", ""),
                    "published_at": pub_date,
                    "symbol": symbol,
                    "category": item.get("category", ""),
                })

            return articles

        except Exception as e:
            logger.error(f"Finnhub stock news error for {symbol}: {e}")
            return []

    async def get_market_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get general market news from Finnhub."""
        if not self.is_configured:
            return []

        try:
            data = await self._get("/news", {"category": "general"})

            if not data or not isinstance(data, list):
                return []

            articles = []
            for item in data[:limit]:
                pub_ts = item.get("datetime")
                pub_date = None
                if pub_ts:
                    try:
                        pub_date = datetime.utcfromtimestamp(int(pub_ts))
                    except (ValueError, TypeError):
                        pub_date = None

                articles.append({
                    "title": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", "finnhub"),
                    "url": item.get("url", ""),
                    "published_at": pub_date,
                    "symbol": None,
                    "category": item.get("category", ""),
                })

            return articles

        except Exception as e:
            logger.error(f"Finnhub market news error: {e}")
            return []

    async def get_fda_calendar(self) -> List[Dict[str, Any]]:
        """Get FDA drug trial calendar (unique to Finnhub free tier)."""
        if not self.is_configured:
            return []

        try:
            data = await self._get("/fda-advisory-committee-calendar")
            if not data or not isinstance(data, list):
                return []

            events = []
            for item in data:
                events.append({
                    "title": item.get("description", ""),
                    "date": item.get("date"),
                    "symbol": None,
                    "source": "fda",
                    "type": "fda_advisory",
                })
            return events

        except Exception as e:
            logger.error(f"Finnhub FDA calendar error: {e}")
            return []


# Singleton
_finnhub_provider: Optional[FinnhubNewsProvider] = None


def get_finnhub_provider() -> FinnhubNewsProvider:
    """Get or create singleton Finnhub provider."""
    global _finnhub_provider
    if _finnhub_provider is None:
        _finnhub_provider = FinnhubNewsProvider()
    return _finnhub_provider
