"""
News Relevance Service — entity resolution between articles and stocks.

CRITICAL RULE: an article is NEVER associated with a stock merely because it
was fetched while processing that stock. Association requires textual evidence
that the article actually references the company or its ticker.

Relevance scale:
  0.95  direct ticker mention ($VOO, NYSE: O, AAPL in headline token form)
  0.75  company/legal-name mention ("Walmart", "Apple Inc.", "Vanguard S&P 500")
  0.50  sector relationship (article about the same sector, no company mention)
  0.20  broad market news
  0.00  unrelated

Short tickers (1-2 chars: O, V, UL) are notoriously ambiguous as substrings,
so they only count with an explicit exchange/list marker ($O, NYSE: O, (O)).
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)

# Well-known company aliases (canonical lowercase). Extended dynamically
# with names from the user's holdings/watchlist at runtime.
_STATIC_ALIASES: Dict[str, List[str]] = {
    "WMT": ["walmart", "wal-mart"],
    "AAPL": ["apple inc", "apple"],
    "MSFT": ["microsoft"],
    "GOOGL": ["alphabet", "google"],
    "AMZN": ["amazon"],
    "META": ["meta platforms", "facebook"],
    "BRK-B": ["berkshire hathaway"],
    "JPM": ["jpmorgan", "jp morgan", "jpmorgan chase"],
    "UNH": ["unitedhealth", "united health"],
    "UL": ["unilever"],
    "O": ["realty income"],
    "LOW": ["lowes companies", "lowe's"],
    "COST": ["costco"],
    "PEP": ["pepsico"],
    "KMB": ["kimberly-clark", "kimberly clark"],
    "TXN": ["texas instruments"],
    "ABBV": ["abbvie"],
    "SBUX": ["starbucks"],
    "AMT": ["american tower"],
    "DHI": ["d.r. horton", "dr horton"],
    "VOO": ["vanguard s&p 500 etf", "vanguard s&p 500", "s&p 500 etf vanguard"],
    "VTI": ["vanguard total stock market", "total stock market etf"],
    "SPY": ["spdr s&p 500", "sp500 etf"],
}

# Words that indicate broad-market coverage when present in a short headline
_MARKET_HINTS = [
    "market", "markets", "stocks", "wall street", "dow", "nasdaq", "s&p",
    "fed", "federal reserve", "inflation", "recession", "treasury",
    "index", "rally", "selloff", "investors", "econom",
]

_SINGLE_WORD_TICKER_CONTEXT = re.compile(
    r"(?:\$([A-Z]{1,5})\b)"                     # $AAPL / $O
    r"|(?:\(([A-Z]{1,5})[:.)]\s*"               # (O: / (AAPL)
    r"|(?:NYSE|NASDAQ|AMEX|OTC)\s*:\s*([A-Z]{1,5})\b)"  # NYSE: O
)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9&'.\- ]+", " ", text.lower())


def _contains_phrase(haystack_norm: str, phrase: str) -> bool:
    """Word-boundary containment check on normalized text."""
    p = _normalize(phrase).strip()
    if not p:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(p).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def _ticker_mentioned(raw_ticker: str, raw_title: str, raw_summary: str) -> bool:
    """
    Does the article explicitly reference this TICKER?
    - >=3 char tickers: word-boundary match in title/summary is acceptable
      (e.g. 'NVDA' as a token), since accidental English collisions are rare.
    - <=2 char tickers (O, V, UL): ONLY explicit markers count ($O, NYSE: O).
    """
    t = raw_ticker.strip().upper()
    title = raw_title or ""
    summary = raw_summary or ""

    if f"${t}" in title or f"${t}" in summary:
        return True
    marker = re.compile(
        r"(?:\(" + re.escape(t) + r"[:.)])"
        r"|(?:(?:NYSE|NASDAQ|AMEX|OTC)\s*:\s*" + re.escape(t) + r"\b)"
        r"|(?:\b" + re.escape(t) + r"\s*:\s*[A-Z])"   # "O: Realty Income..."
    )
    if marker.search(title) or marker.search(summary):
        return True

    if len(t) >= 3:
        pat = re.compile(r"(?<![A-Z0-9])" + re.escape(t) + r"(?![A-Z0-9])")
        if pat.search(title.upper()) or pat.search(summary.upper()):
            return True
    # 1-2 char tickers without explicit markers: NOT evidence
    return False


class NewsRelevanceService:
    """
    Scores article<->stock relationships with textual evidence.
    """

    def __init__(self):
        self._aliases: Dict[str, List[str]] = {
            sym: list(als) for sym, als in _STATIC_ALIASES.items()
        }

    def register_company(self, symbol: str, name: Optional[str],
                         extra_aliases: Optional[List[str]] = None):
        """Register a company's names so its articles can be matched by name."""
        sym = symbol.strip().upper()
        aliases = list(self._aliases.get(sym, []))
        if name:
            n = _normalize(name)
            # Strip legal suffixes for better matching
            for suf in (" inc", " corp", " corporation", " ltd", " plc",
                        " incorporated", " company", " co", " etf", " trust"):
                if n.endswith(suf):
                    n = n[: -len(suf)]
            if len(n) >= 3 and n not in aliases:
                aliases.insert(0, n)
        for a in (extra_aliases or []):
            na = _normalize(a)
            if na and na not in aliases:
                aliases.append(na)
        self._aliases[sym] = aliases

    def score_article(self, title: str, summary: str, symbol: str) -> float:
        """
        Evidence-based relevance of an article to a specific symbol.
        Returns 0.0-0.95. Never returns a positive score without evidence.
        """
        sym = symbol.strip().upper()

        # 1. Direct ticker evidence
        if _ticker_mentioned(sym, title, summary):
            return 0.95

        # 2. Company-name evidence (registered aliases incl. canonical name)
        text_norm = _normalize(f"{title}. {summary}")
        for alias in self._aliases.get(sym, []):
            if _contains_phrase(text_norm, alias):
                return 0.75
        return 0.0

    def classify_article_scope(self, title: str, summary: str) -> str:
        """MARKET | GENERAL — used when no company matched."""
        text_norm = _normalize(f"{title}. {summary}")
        if any(_contains_phrase(text_norm, hint) for hint in _MARKET_HINTS):
            return "MARKET"
        return "GENERAL"

    def attach_relevance(
        self,
        articles: List[Dict[str, Any]],
        symbol: str,
        company_name: Optional[str] = None,
        min_threshold: float = 0.70,
    ) -> List[Dict[str, Any]]:
        """
        Filter+annotate articles claimed for one symbol.
        Articles below min_threshold are DROPPED, not mislabeled.
        Each surviving article gets:
          relevance_score, relevance_class ('COMPANY'), evidence string.
        """
        self.register_company(symbol, company_name)
        kept: List[Dict[str, Any]] = []
        for art in articles:
            title = art.get("title") or ""
            summary = art.get("summary") or ""
            score = self.score_article(title, summary, symbol)

            # If provider already asserted a symbol AND our check passes, keep 0.95.
            # If provider asserted a symbol but NO textual evidence exists,
            # drop it — that's exactly the Walmart/O class of bug.
            if score < min_threshold:
                continue

            annotated = dict(art)
            annotated["symbol"] = symbol
            annotated["relevance_score"] = round(score, 2)
            annotated["relevance_class"] = "COMPANY"
            annotated["relevance_evidence"] = (
                "ticker explicitly referenced" if score >= 0.95 else "company name referenced"
            )
            kept.append(annotated)
        return kept

    def resolve_universe(
        self,
        articles: List[Dict[str, Any]],
        universe: Dict[str, Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Resolve many articles against many companies.
        universe: {symbol: {"name": ..., "sector": ...}}
        Returns {symbol: [articles]} containing ONLY evidenced associations.
        Unmatched articles are returned under "_unassigned".
        """
        for sym, meta in universe.items():
            self.register_company(sym, meta.get("name"))

        by_symbol: Dict[str, List[Dict[str, Any]]] = {sym: [] for sym in universe}
        by_symbol["_unassigned"] = []
        seen_hashes: Set[str] = set()
        for art in articles:
            key = (art.get("content_hash") or art.get("url") or art.get("title", ""))
            if key and key in seen_hashes:
                continue
            if key:
                seen_hashes.add(key)

            best_sym, best_score = None, 0.0
            for sym in universe:
                score = self.score_article(
                    art.get("title") or "", art.get("summary") or "", sym
                )
                if score > best_score:
                    best_sym, best_score = sym, score

            if best_sym and best_score >= 0.70:
                annotated = dict(art)
                annotated["symbol"] = best_sym
                annotated["relevance_score"] = round(best_score, 2)
                annotated["relevance_class"] = "COMPANY"
                by_symbol.setdefault(best_sym, []).append(annotated)
            else:
                scope = self.classify_article_scope(
                    art.get("title") or "", art.get("summary") or ""
                )
                annotated = dict(art)
                annotated["symbol"] = None
                annotated["relevance_score"] = 0.20 if scope == "MARKET" else 0.05
                annotated["relevance_class"] = scope
                by_symbol["_unassigned"].append(annotated)
        return by_symbol


# Singleton
_relevance_service: Optional[NewsRelevanceService] = None


def get_news_relevance_service() -> NewsRelevanceService:
    global _relevance_service
    if _relevance_service is None:
        _relevance_service = NewsRelevanceService()
    return _relevance_service