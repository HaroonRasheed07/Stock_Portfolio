"""
RSS feed news provider.
Aggregates from reputable free financial RSS feeds.
No API key required.
"""
import logging
import asyncio
import hashlib
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET

import httpx

from app.providers.base import NewsProvider

logger = logging.getLogger(__name__)

# Reputable free financial RSS feeds
FINANCIAL_RSS_FEEDS = [
    {
        "name": "MarketWatch",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
        "category": "market_news",
    },
    {
        "name": "CNBC",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "category": "market_news",
    },
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "category": "market_news",
    },
    {
        "name": "Investing.com",
        "url": "https://www.investing.com/rss/news.rss",
        "category": "investing",
    },
    {
        "name": "Seeking Alpha",
        "url": "https://seekingalpha.com/market_currents.xml",
        "category": "market_analysis",
    },
]

# Company-specific RSS patterns (YFinance news has no RSS, but some sources do)
SYMBOL_NEWS_FEEDS = {
    "FDA": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
}


class RSSNewsProvider(NewsProvider):
    """
    RSS feed aggregator for financial news.
    No API key required. Fetches from multiple reputable free sources.
    """

    def __init__(self):
        self._last_fetch: Optional[datetime] = None
        self._cache: List[Dict[str, Any]] = []
        self._cache_ttl = 600  # 10 minutes
        self._executor = ThreadPoolExecutor(max_workers=4)

    def _parse_rss_date(self, date_str: str) -> Optional[datetime]:
        """Parse various RSS date formats."""
        if not date_str:
            return None
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%a, %d %b %Y %H:%M:%S %z",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                return dt
            except ValueError:
                continue
        return None

    def _parse_xml(self, xml_text: str, feed_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse RSS/Atom XML into normalized articles."""
        articles = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        # Handle RSS 2.0
        items = root.findall(".//item")
        if not items:
            # Try Atom format
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//atom:entry", ns)

        for item in items:
            title = ""
            summary = ""
            url = ""
            pub_date = None

            # RSS 2.0
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                title = title_el.text.strip()

            desc_el = item.find("description")
            if desc_el is not None and desc_el.text:
                # Strip HTML tags
                summary = re.sub(r"<[^>]+>", "", desc_el.text).strip()

            link_el = item.find("link")
            if link_el is not None:
                if link_el.text:
                    url = link_el.text.strip()
                elif link_el.get("href"):
                    url = link_el.get("href").strip()

            pub_el = item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}published")
            if pub_el is not None and pub_el.text:
                pub_date = self._parse_rss_date(pub_el.text)

            # Atom fallback
            if not url:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    url = link_el.get("href", "")

            if not title:
                continue

            content_hash = hashlib.md5(f"{title}:{url}".encode()).hexdigest()

            articles.append({
                "title": title,
                "summary": summary[:500] if summary else "",
                "source": feed_info.get("name", "RSS"),
                "url": url,
                "published_at": pub_date,
                "symbol": None,
                "content_hash": content_hash,
                "feed_category": feed_info.get("category", ""),
            })

        return articles

    async def _fetch_feed(self, feed_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(feed_info["url"], headers=headers)
                if resp.status_code == 200:
                    xml_text = resp.text
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        self._executor,
                        self._parse_xml,
                        xml_text,
                        feed_info,
                    )
                else:
                    logger.debug(f"RSS feed {feed_info['name']} returned {resp.status_code}")
                    return []
        except Exception as e:
            logger.debug(f"Failed to fetch RSS feed {feed_info['name']}: {e}")
            return []

    async def get_stock_news(
        self, symbol: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get news for a specific stock from RSS feeds.
        Uses evidence-based entity resolution: an article is only associated
        with the symbol when the ticker or company name is actually referenced.
        Prevents false associations (e.g. a Walmart article matching ticker O).
        """
        from app.services.news_relevance_service import get_news_relevance_service

        all_news = await self.get_market_news(limit=100)
        relevance = get_news_relevance_service()

        # Look up registered company name if available
        company_name = None
        try:
            from app.utils.stock_directory import lookup_company_name
            company_name = lookup_company_name(symbol)
        except Exception:
            pass

        matched = relevance.attach_relevance(all_news, symbol, company_name,
                                             min_threshold=0.70)
        return matched[:limit]

    async def get_market_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get general market news from all configured RSS feeds."""
        import time

        # Check cache freshness
        now = datetime.utcnow()
        if (self._cache and self._last_fetch and
                (now - self._last_fetch).total_seconds() < self._cache_ttl):
            return self._cache[:limit]

        # Fetch all feeds concurrently
        tasks = [self._fetch_feed(feed) for feed in FINANCIAL_RSS_FEEDS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)

        # Deduplicate by content hash
        seen_hashes = set()
        unique_articles = []
        for article in all_articles:
            h = article.get("content_hash", "")
            if h and h not in seen_hashes:
                seen_hashes.add(h)
                unique_articles.append(article)

        # Sort by date (newest first)
        unique_articles.sort(
            key=lambda x: x.get("published_at") or datetime.min,
            reverse=True,
        )

        self._cache = unique_articles
        self._last_fetch = now

        return unique_articles[:limit]


# Singleton
_rss_provider: Optional[RSSNewsProvider] = None


def get_rss_provider() -> RSSNewsProvider:
    """Get or create singleton RSS provider."""
    global _rss_provider
    if _rss_provider is None:
        _rss_provider = RSSNewsProvider()
    return _rss_provider
