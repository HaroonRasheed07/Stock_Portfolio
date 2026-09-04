"""
Analysis service — orchestrates technical, fundamental, risk, diversification,
recommendation, news, catalyst, and ML engines.
"""
import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import pandas as pd

from app.services.portfolio_service import PortfolioService
from app.services.stock_service import StockService
from app.engines.technical import TechnicalEngine
from app.engines.fundamental import FundamentalEngine
from app.engines.risk import RiskEngine
from app.engines.diversification import DiversificationEngine
from app.engines.recommendation import RecommendationEngine
from app.engines.sentiment import SentimentEngine
from app.engines.catalyst import CatalystEngine
from app.engines.ml_models import MLEngine
from app.ai.rule_based import RuleBasedAI
from app.models.settings import UserSettings

logger = logging.getLogger(__name__)

# Server-side result caches so heavy scans are NOT recomputed on every page load
_result_cache: Dict[str, tuple] = {}  # key -> (data, timestamp)
_RESULT_TTL = 900  # 15 minutes

# Request coalescing: if scan A is running, scan B awaits A's result
_inflight_scans: Dict[str, asyncio.Future] = {}


def _get_cached_result(key: str) -> Optional[Any]:
    cached = _result_cache.get(key)
    if cached and (time.time() - cached[1]) < _RESULT_TTL:
        return cached[0]
    return None


def _set_cached_result(key: str, data: Any):
    import time as _t
    _result_cache[key] = (data, _t.time())


class AnalysisService:
    """Orchestrates comprehensive analytics operations."""

    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.stock_service = StockService(db)

        # Engines
        self.technical_engine = TechnicalEngine()
        self.fundamental_engine = FundamentalEngine()
        self.risk_engine = RiskEngine()
        self.diversification_engine = DiversificationEngine()
        self.recommendation_engine = RecommendationEngine()
        self.sentiment_engine = SentimentEngine()
        self.catalyst_engine = CatalystEngine()
        self.ml_engine = MLEngine()
        self.rule_ai = RuleBasedAI()

    def _resolve_scan_symbols(self, universe: str, selected_symbols: Optional[List[str]] = None
                               ) -> tuple:
        """Resolve which symbols to scan based on universe mode.

        Returns:
            (symbols_to_scan, portfolio_symbols)
            symbols_to_scan: list of dicts with at least 'symbol', 'name', 'sector' keys
            portfolio_symbols: set of symbols that are in the portfolio
        """
        from app.models.watchlist import WatchlistItem
        from app.services.ticker_service import get_ticker_service

        ticker_svc = get_ticker_service()
        portfolio_symbols = set()

        if universe == "portfolio":
            holdings = self.portfolio_service.get_holdings()
            portfolio_symbols = {h["symbol"] for h in holdings}
            return holdings, portfolio_symbols

        elif universe == "watchlist":
            items = self.db.query(WatchlistItem).all()
            symbols = []
            for item in items:
                normalized = ticker_svc.normalize(item.symbol)
                if not normalized:
                    normalized = item.symbol.upper()
                symbols.append({
                    "symbol": normalized,
                    "name": item.name,
                    "sector": None,
                    "current_price": None,
                    "current_value": None,
                    "quantity": None,
                    "avg_price": None,
                    "allocation_pct": 0,
                    "unrealized_gain_pct": None,
                })
            return symbols, portfolio_symbols

        elif universe == "portfolio_watchlist":
            holdings = self.portfolio_service.get_holdings()
            portfolio_symbols = {h["symbol"] for h in holdings}
            items = self.db.query(WatchlistItem).all()
            watchlist_map = {}
            for item in items:
                normalized = ticker_svc.normalize(item.symbol)
                if not normalized:
                    normalized = item.symbol.upper()
                watchlist_map[normalized] = {
                    "symbol": normalized,
                    "name": item.name,
                    "sector": None,
                    "current_price": None,
                    "current_value": None,
                    "quantity": None,
                    "avg_price": None,
                    "allocation_pct": 0,
                    "unrealized_gain_pct": None,
                }
            # Merge: portfolio holdings take precedence (they have richer data)
            seen = set()
            merged = []
            for h in holdings:
                merged.append(h)
                seen.add(h["symbol"])
            for sym, wdata in watchlist_map.items():
                if sym not in seen:
                    merged.append(wdata)
                    seen.add(sym)
            return merged, portfolio_symbols

        elif universe == "selected":
            validated = []
            seen = set()
            for sym in (selected_symbols or []):
                normalized = ticker_svc.normalize(sym)
                if not normalized:
                    normalized = sym.upper().strip()
                if not normalized or len(normalized) > 10:
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                validated.append({
                    "symbol": normalized,
                    "name": None,
                    "sector": None,
                    "current_price": None,
                    "current_value": None,
                    "quantity": None,
                    "avg_price": None,
                    "allocation_pct": 0,
                    "unrealized_gain_pct": None,
                })
            return validated, portfolio_symbols

        # Default: portfolio
        holdings = self.portfolio_service.get_holdings()
        portfolio_symbols = {h["symbol"] for h in holdings}
        return holdings, portfolio_symbols

    def _get_user_risk_profile(self) -> str:
        """Get the active user's risk profile preference."""
        settings = self.db.query(UserSettings).first()
        return settings.risk_profile if settings else "moderate"

    def _get_investment_style(self) -> str:
        """Get the active user's investment style preference."""
        settings = self.db.query(UserSettings).first()
        return settings.investment_style if settings else "balanced"

    async def get_full_stock_analysis(self, symbol: str) -> Dict[str, Any]:
        """Run complete 360-degree analysis for a stock."""
        # 1. Fetch data in parallel (reduces from ~6 sequential calls to ~3)
        overview, hist_prices, news, earnings = await asyncio.gather(
            self.stock_service.get_stock_overview(symbol),
            self.stock_service.get_historical_prices(symbol, period="1y"),
            self.stock_service.get_stock_news(symbol, limit=15),
            self.stock_service.get_earnings_data(symbol),
        )
        
        price_data = overview.get("price", {})
        current_price = price_data.get("price") or 0.0

        df_hist = pd.DataFrame(hist_prices)
        if not df_hist.empty and "date" in df_hist.columns:
            df_hist.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)

        # 2. Run engines
        fundamental = self.fundamental_engine.analyze(overview.get("key_metrics", {}))
        technical = self.technical_engine.analyze(df_hist, current_price)
        risk = self.risk_engine.analyze_stock(df_hist, overview.get("key_metrics", {}).get("beta"))
        sentiment = self.sentiment_engine.analyze_articles(news)
        catalysts = self.catalyst_engine.get_all_catalysts(news, earnings, overview.get("key_metrics", {}))
        ml_prediction = self.ml_engine.predict_trend(df_hist)

        # Check holding context
        holdings = self.portfolio_service.get_holdings()
        holding_info = next((h for h in holdings if h["symbol"] == symbol), None)
        allocation = holding_info.get("allocation_pct", 0) if holding_info else 0
        gain_pct = holding_info.get("unrealized_gain_pct") if holding_info else None

        risk_profile = self._get_user_risk_profile()
        investment_style = self._get_investment_style()

        # Recommendation
        recommendation = self.recommendation_engine.recommend(
            symbol=symbol,
            fundamental_score=fundamental.get("score", 50),
            fundamental_data=fundamental,
            technical_data=technical,
            risk_data=risk,
            sentiment_data=sentiment,
            catalyst_data=catalysts,
            portfolio_allocation=allocation,
            unrealized_gain_pct=gain_pct,
            risk_profile=risk_profile,
            investment_style=investment_style,
        )

        return {
            "symbol": symbol,
            "overview": overview,
            "fundamental": fundamental,
            "technical": technical,
            "risk": risk,
            "sentiment": sentiment,
            "catalysts": catalysts,
            "ml_prediction": ml_prediction,
            "recommendation": recommendation,
            "holding_context": holding_info,
            "news": news[:8],
        }

    async def get_portfolio_health_report(self, force: bool = False) -> Dict[str, Any]:
        """Generate full portfolio health report (batched + 15-min result cache)."""
        if not force:
            cached = _get_cached_result("portfolio_health")
            if cached is not None:
                return cached

        summary = self.portfolio_service.get_portfolio_summary()
        holdings = self.portfolio_service.get_holdings()

        # ONE batched yfinance download serves every holding's 1y history
        symbols = [h["symbol"] for h in holdings]
        hist_rows = await self.stock_service.get_batch_historical_prices(symbols, period="1y")

        hist_data: Dict[str, pd.DataFrame] = {}
        failed_symbols: List[str] = []
        for sym, rows in hist_rows.items():
            if not rows:
                failed_symbols.append(sym)
                continue
            df = pd.DataFrame(rows)
            if not df.empty and "close" in df.columns:
                df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
                hist_data[sym] = df

        # Run risk and diversification OFF the event loop
        loop = asyncio.get_event_loop()
        risk, diversification = await asyncio.gather(
            loop.run_in_executor(None, lambda: self.risk_engine.analyze_portfolio(holdings, hist_data)),
            loop.run_in_executor(None, lambda: self.diversification_engine.analyze(holdings, hist_data)),
        )

        # Get news for top holdings (bounded, with circuit breaker check)
        from app.utils.resilience import get_circuit_breaker
        breaker = get_circuit_breaker("yahoo")
        top_symbols = [h["symbol"] for h in holdings[:5]]
        if breaker.allow_request():
            news_results = await asyncio.gather(
                *[self.stock_service.get_stock_news(sym, limit=3) for sym in top_symbols]
            )
            all_news = [n for batch in news_results for n in batch]
        else:
            all_news = []

        # Data quality: how many holdings actually had analyzable history?
        analyzed = sum(1 for df in hist_data.values() if df is not None and len(df) >= 60)
        missing_symbols = [h["symbol"] for h in holdings if h["symbol"] not in hist_data]

        # Per-holding technical + fundamental analysis (reuses already-fetched data)
        per_holding_analysis = {}
        for h in holdings:
            sym = h["symbol"]
            df = hist_data.get(sym)
            if df is None or len(df) < 60:
                continue
            try:
                current_price = float(df["Close"].iloc[-1])
                technical = self.technical_engine.analyze(df, current_price)
                info = await self.stock_service.get_stock_info(sym)
                if info and not info.get("error"):
                    metrics = {k: info.get(k) for k in [
                        "pe_ratio", "forward_pe", "peg_ratio", "price_to_book",
                        "price_to_sales", "ev_to_ebitda", "profit_margin",
                        "operating_margin", "gross_margin", "revenue", "revenue_growth",
                        "earnings", "eps", "dividend_yield", "roe", "debt_to_equity",
                        "free_cash_flow",
                    ]}
                    fundamental = self.fundamental_engine.analyze(metrics)
                else:
                    fundamental = {"score": 50, "strengths": [], "weaknesses": []}
                per_holding_analysis[sym] = {
                    "technical": technical,
                    "fundamental": fundamental,
                }
            except Exception:
                pass

        report = self.rule_ai.generate_portfolio_health_report(
            summary=summary,
            risk=risk,
            diversification=diversification,
            holdings=holdings,
            news=all_news,
            per_holding_analysis=per_holding_analysis,
        )

        # Determine data_status
        if not holdings:
            data_status = "success"
        elif analyzed == len(holdings):
            data_status = "success"
        elif analyzed > 0:
            data_status = "partial"
        elif failed_symbols:
            data_status = "provider_unavailable"
        else:
            data_status = "success"

        report["data_quality"] = {
            "total_holdings": len(holdings),
            "analyzed_holdings": analyzed,
            "missing_history": missing_symbols,
            "failed_symbols": failed_symbols,
            "completeness_pct": round(analyzed / len(holdings) * 100, 1) if holdings else 0,
            "data_status": data_status,
            "message": (
                f"{analyzed}/{len(holdings)} holdings analyzed"
                if holdings else "No holdings"
            ),
        }
        _set_cached_result("portfolio_health", report)
        return report

    async def get_trading_opportunities(self, force: bool = False, universe: str = "portfolio",
                                         selected_symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Identify swing setups among the specified universe.
        Uses request coalescing: if scan A is running, scan B awaits A's result.
        Returns { opportunities: [...], data_status: ... }.
        Results cached 15 minutes.
        """
        cache_key = f"trading_opportunities:{universe}"
        if universe == "selected" and selected_symbols:
            cache_key += f":{','.join(sorted(selected_symbols))}"
        if not force:
            cached = _get_cached_result(cache_key)
            if cached is not None:
                return cached

        # CRITICAL: Even with force=True, check if a scan is already in-flight.
        # This prevents duplicate batch downloads when multiple refresh requests arrive.
        existing = _inflight_scans.get(cache_key)
        if existing is not None:
            try:
                return await asyncio.shield(existing)
            except Exception:
                pass

        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        _inflight_scans[cache_key] = fut
        try:
            # Resolve scan symbols based on universe mode
            symbols_to_scan, portfolio_symbols = self._resolve_scan_symbols(
                universe, selected_symbols
            )
            result = await self._do_trading_scan(symbols_to_scan, portfolio_symbols, universe)
            if not fut.done():
                fut.set_result(result)
            # Cache result even if stale — it's still better than nothing
            _set_cached_result(cache_key, result)
            return result
        except Exception as e:
            if not fut.done():
                fut.set_exception(e)
            raise
        finally:
            _inflight_scans.pop(cache_key, None)

    async def _do_trading_scan(self, symbols_to_scan: Optional[List[Dict]] = None,
                                portfolio_symbols: Optional[set] = None,
                                universe: str = "portfolio") -> Dict[str, Any]:
        """Actual trading opportunities scan logic (runs at most once per 15 min).
        
        CRITICAL RESILIENCE:
        - News failure does NOT kill technical opportunity calculation
        - One ticker failure does NOT kill entire scan
        - Partial results are always returned when available
        - Per-ticker timeout prevents hung requests
        - Stale cache is used when provider is unavailable
        - Cold cache: eligibility does NOT require current_price (CSV imports
          may not have it yet; batch historical works independently).
        - Total scan deadline enforced (120s hard limit)
        """
        scan_start = time.time()
        MAX_SCAN_SECONDS = 120

        # ── STAGE 1: Holdings + Eligibility ─────────────────────
        if symbols_to_scan is not None:
            all_holdings = symbols_to_scan
        else:
            all_holdings = self.portfolio_service.get_holdings()
        if portfolio_symbols is None:
            portfolio_symbols = {h["symbol"] for h in all_holdings}

        eligible = []
        excluded_reasons = {}
        for h in all_holdings:
            price = h.get("current_price") or h.get("avg_price") or 0
            if price and price >= 5.0:
                eligible.append(h)
            elif h.get("current_value") and h.get("quantity"):
                try:
                    derived = h["current_value"] / h["quantity"]
                    if derived >= 5.0:
                        eligible.append(h)
                    else:
                        excluded_reasons[h["symbol"]] = f"derived_price={derived:.2f}"
                except (TypeError, ZeroDivisionError) as e:
                    excluded_reasons[h["symbol"]] = f"calc_error={e}"
            elif universe in ("watchlist", "selected", "portfolio_watchlist"):
                # For non-portfolio universes, include symbols without price data
                # (price filter happens after historical data is fetched)
                eligible.append(h)
            else:
                excluded_reasons[h["symbol"]] = (
                    f"price={price} value={h.get('current_value')} qty={h.get('quantity')}"
                )
        symbols = [h["symbol"] for h in eligible]

        logger.info(
            f"TRADING_SCAN_START: holdings={len(all_holdings)} eligible={len(eligible)} "
            f"excluded={len(excluded_reasons)} "
            f"symbols={','.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}"
        )
        if excluded_reasons:
            for sym, reason in excluded_reasons.items():
                logger.warning(f"TRADING_SCAN_EXCLUDED: {sym} — {reason}")

        # ── STAGE 2: Batch Historical Data ──────────────────────
        t0 = time.time()
        hist_rows = await self.stock_service.get_batch_historical_prices(symbols, period="1y")
        hist_elapsed = time.time() - t0

        total_eligible = len(eligible)
        symbols_with_data = sum(1 for h in eligible if hist_rows.get(h["symbol"]))
        symbols_failed = [h["symbol"] for h in eligible if not hist_rows.get(h["symbol"])]

        # Detect if we're using stale data
        data_source = "live"
        stale_age = None
        if symbols_with_data > 0 and symbols_with_data < total_eligible:
            data_source = "partial"
        if symbols_failed and symbols_with_data == 0:
            data_source = "provider_unavailable"
        elif symbols_failed and symbols_with_data > 0:
            from app.utils.resilience import get_circuit_breaker
            breaker = get_circuit_breaker("yahoo")
            if not breaker.allow_request():
                data_source = "stale"
                stale_age = "recent cache (provider unavailable)"

        logger.info(
            f"TRADING_SCAN_HISTORICAL: {symbols_with_data}/{total_eligible} with data "
            f"({hist_elapsed:.1f}s) source={data_source} "
            f"failed={symbols_failed[:5]}{'...' if len(symbols_failed) > 5 else ''}"
        )

        # Stage 1: cheap technical pre-filter
        candidates = []
        for h in eligible:
            symbol = h["symbol"]
            rows = hist_rows.get(symbol) or []
            df_hist = pd.DataFrame(rows)
            if df_hist.empty or len(df_hist) < 60 or "close" not in df_hist.columns:
                continue
            df_hist.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume"
            }, inplace=True)

            current_price = float(df_hist["Close"].iloc[-1]) or h.get("current_price") or 0
            if not current_price:
                continue

            technical = self.technical_engine.analyze(df_hist, current_price)
            signals = [s["signal"] for s in technical.get("signals", [])]
            trend = technical.get("trend", "Neutral")

            setup_found = None
            momentum = technical.get("momentum", "")
            # Setup 1: Pullback in uptrend — RSI < 40 (not just 30) in any positive trend
            if "RSI Oversold" in signals and trend in ("Uptrend", "Strong Uptrend", "Neutral"):
                setup_found = "Pullback in Uptrend (RSI Oversold)"
            # Setup 1b: RSI approaching oversold in strong uptrend
            elif any(s.get("signal") == "RSI Approaching Oversold" for s in technical.get("signals", [])) and trend in ("Uptrend", "Strong Uptrend"):
                setup_found = "Pullback in Uptrend (RSI Approaching Oversold)"
            # Setup 2: Golden Cross — accept both "Bullish" and "Strong Bullish"
            elif "Golden Cross Active" in signals and ("Bullish" in momentum or "Strong Bullish" in momentum):
                setup_found = "Golden Cross Momentum Breakout"
            # Setup 3: Bollinger Band breakout
            elif "Above Upper Bollinger" in signals:
                setup_found = "Bollinger Band Volatility Expansion"
            # Setup 4: MACD Bullish Crossover in uptrend
            elif "MACD Bullish" in signals and trend in ("Uptrend", "Strong Uptrend"):
                setup_found = "MACD Bullish Crossover"
            # Setup 5: Price bouncing off support
            elif "Near Support" in signals and trend in ("Uptrend", "Neutral"):
                setup_found = "Support Bounce Setup"
            # Setup 6: Volume breakout with bullish momentum
            elif "Volume Spike" in signals and "Bullish" in momentum:
                setup_found = "Volume Breakout"

            if setup_found:
                candidates.append((h, technical, current_price, signals, trend, df_hist))

        # Stage 2: fundamentals only for setup candidates (DB-cached 12h)
        # BOUNDED CONCURRENCY: max 3 parallel info calls to prevent storms
        from app.utils.resilience import get_circuit_breaker
        breaker = get_circuit_breaker("yahoo")
        _info_semaphore = asyncio.Semaphore(3)
        _PER_TICKER_TIMEOUT = 30  # seconds per candidate qualification

        async def _qualify(h, technical, current_price, signals, trend, df_hist) -> Optional[Dict[str, Any]]:
            symbol = h["symbol"]
            try:
                # Check circuit breaker before each info call
                if not breaker.allow_request():
                    logger.debug(f"Trading: skipping {symbol} — circuit breaker open")
                    return None
                async with _info_semaphore:
                    # Per-ticker timeout prevents one slow ticker from blocking all
                    try:
                        info = await asyncio.wait_for(
                            self.stock_service.get_stock_info(symbol),
                            timeout=_PER_TICKER_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Trading: {symbol} info timed out after {_PER_TICKER_TIMEOUT}s")
                        return None
                if not info or info.get("error"):
                    return None
                metrics = {
                    "pe_ratio": info.get("pe_ratio"),
                    "forward_pe": info.get("forward_pe"),
                    "peg_ratio": info.get("peg_ratio"),
                    "price_to_book": info.get("price_to_book"),
                    "price_to_sales": info.get("price_to_sales"),
                    "ev_to_ebitda": info.get("ev_to_ebitda"),
                    "profit_margin": info.get("profit_margin"),
                    "operating_margin": info.get("operating_margin"),
                    "gross_margin": info.get("gross_margin"),
                    "revenue": info.get("revenue"),
                    "revenue_growth": info.get("revenue_growth"),
                    "earnings": info.get("earnings"),
                    "eps": info.get("eps"),
                    "dividend_yield": info.get("dividend_yield"),
                    "roe": info.get("roe"),
                    "debt_to_equity": info.get("debt_to_equity"),
                    "free_cash_flow": info.get("free_cash_flow"),
                }
                fundamental = self.fundamental_engine.analyze(metrics)
                if fundamental.get("score", 0) < 30:
                    return None
                setup = signals and (
                    "Pullback in Uptrend (RSI Oversold)" if "RSI Oversold" in signals else
                    "Golden Cross Momentum Breakout" if "Golden Cross Active" in signals else
                    "Bollinger Band Volatility Expansion"
                )

                # ── Maturity model ──────────────────────────
                maturity = self._classify_maturity(technical, signals, trend, setup)
                validity = self._classify_validity(setup, trend)
                why_now = self._generate_why_now(setup, signals, technical, trend)
                rank_score = self._score_opportunity(
                    setup, technical, fundamental, trend, maturity,
                )

                # ── Granular scores ──────────────────────────
                technical_score = round(technical.get("trend_strength", 50), 1)
                fundamental_score = round(fundamental.get("score", 50), 1)

                # Risk assessment from actual risk engine
                try:
                    import pandas as _pd
                    risk_data = self.risk_engine.analyze_stock(df_hist)
                    actual_risk = risk_data.get("risk_level", "Moderate")
                    risk_score_val = risk_data.get("risk_score", 50)
                except Exception:
                    actual_risk = "Moderate"
                    risk_score_val = 50

                # Catalyst + sentiment from news
                # CRITICAL: News failure does NOT kill technical opportunity calculation
                catalyst_score = None
                sentiment_data = None
                news_unavailable = False
                try:
                    news_items = await asyncio.wait_for(
                        self.stock_service.get_stock_news(symbol, limit=5),
                        timeout=15,  # news should not block trading scan
                    )
                    if news_items:
                        sentiment_data = self.sentiment_engine.analyze_articles(news_items)
                        # Catalyst score: positive sentiment + high impact keywords boost
                        sent_score = sentiment_data.get("overall_score", 0)
                        pos_count = sentiment_data.get("positive_count", 0)
                        neg_count = sentiment_data.get("negative_count", 0)
                        catalyst_score = round(min(100, max(0, 50 + sent_score * 30 + (pos_count - neg_count) * 5)), 1)
                    else:
                        news_unavailable = True
                except (asyncio.TimeoutError, Exception):
                    news_unavailable = True

                # Confidence: composite of available factor scores
                factor_scores = [technical_score, fundamental_score]
                if catalyst_score is not None:
                    factor_scores.append(catalyst_score)
                confidence = round(sum(factor_scores) / len(factor_scores), 1) if factor_scores else 50

                # Estimated horizon from ATR, trend, and momentum
                indicators = technical.get("indicators", {})
                atr = indicators.get("atr")
                estimated_horizon = self._estimate_horizon(setup, trend, technical.get("momentum", "Neutral"), atr, current_price)

                # Entry zone from support/resistance
                support = technical.get("support_levels", [])
                resistance = technical.get("resistance_levels", [])
                entry_zone = None
                if support or resistance:
                    entry_zone = {
                        "support": support[0] if support else None,
                        "resistance": resistance[0] if resistance else None,
                        "current_price": current_price,
                    }

                # Late entry detection: how much has price moved from ideal entry
                late_entry_pct = self._compute_late_entry_pct(setup, technical, current_price)

                # Entry status: is this still actionable or has price moved too far?
                entry_status = self._compute_entry_status(late_entry_pct, trend, maturity)

                # Rename market_cap to actual portfolio value
                portfolio_value = h.get("current_value")

                # ── Target & Stop from technical levels ─────────
                atr = indicators.get("atr_14", 0)
                target_price = resistance[0] if resistance else None
                stop_price = support[0] if support else None
                if not stop_price and atr and current_price:
                    stop_price = round(current_price - 2 * atr, 2)
                risk_reward = None
                if target_price and stop_price and stop_price < current_price:
                    upside = target_price - current_price
                    downside = current_price - stop_price
                    if downside > 0:
                        risk_reward = round(upside / downside, 2)

                # Per-symbol data status
                hist_age_hours = None
                try:
                    from app.models.cache import HistoricalPriceCache
                    hcache = self.db.query(HistoricalPriceCache).filter(
                        HistoricalPriceCache.symbol == symbol,
                        HistoricalPriceCache.period == "1y",
                    ).first()
                    if hcache and hcache.cached_at:
                        hist_age_hours = round((pd.Timestamp.utcnow() - pd.Timestamp(hcache.cached_at)).total_seconds() / 3600, 1)
                except Exception:
                    pass

                # Score breakdown for "Why this score?" feature
                score_breakdown = self._compute_score_breakdown(
                    technical, fundamental, trend, maturity, setup, indicators,
                )

                # Setup freshness based on age and price movement
                freshness = self._classify_freshness(
                    maturity, entry_status, late_entry_pct, trend,
                )

                # Portfolio context
                allocation_pct = h.get("allocation_pct", 0)
                unrealized_gain_pct = h.get("unrealized_gain_pct")
                current_value = h.get("current_value")
                quantity = h.get("quantity")
                avg_price = h.get("avg_price")

                # News items with timestamps for frontend display
                news_display = []
                try:
                    raw_news = await asyncio.wait_for(
                        self.stock_service.get_stock_news(symbol, limit=3),
                        timeout=10,
                    )
                    for item in (raw_news or []):
                        pub_time = item.get("publishedAt") or item.get("published_at") or ""
                        if not pub_time:
                            pub_time = item.get("providerPublishTime")
                            if pub_time and isinstance(pub_time, (int, float)):
                                from datetime import datetime as _dt
                                try:
                                    pub_time = _dt.utcfromtimestamp(pub_time).isoformat() + "Z"
                                except Exception:
                                    pub_time = ""
                        news_display.append({
                            "headline": item.get("title", ""),
                            "source": item.get("publisher", ""),
                            "published_at": pub_time,
                            "sentiment": None,
                        })
                except Exception:
                    pass

                return {
                    "symbol": symbol,
                    "name": h.get("name") or info.get("name"),
                    "setup": setup,
                    "signal": "BUY" if maturity in ("CONFIRMED", "MATURE") and entry_status == "ACTIONABLE" else
                              "WATCH" if maturity in ("DEVELOPING", "EARLY") or entry_status == "ACTIONABLE" else
                              "HOLD" if entry_status == "EXTENDED" else "AVOID",
                    "trend": trend,
                    "momentum": technical.get("momentum", "Neutral"),
                    "catalyst": catalyst_score,
                    "sentiment": sentiment_data.get("overall_sentiment") if sentiment_data else None,
                    "risk": actual_risk,
                    "risk_score": risk_score_val,
                    "maturity": maturity,
                    "validity": validity,
                    "freshness": freshness,
                    "entry_status": entry_status,
                    "rank_score": rank_score,
                    "technical_score": technical_score,
                    "fundamental_score": fundamental_score,
                    "catalyst_score": catalyst_score,
                    "confidence": confidence,
                    "score_breakdown": score_breakdown,
                    "estimated_horizon": estimated_horizon,
                    "entry_zone": entry_zone,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "risk_reward": risk_reward,
                    "late_entry_pct": late_entry_pct,
                    "why_now": why_now,
                    "potential_upside": round(
                        (target_price / current_price * 100 - 100), 1
                    ) if target_price and current_price else None,
                    "technical_factors": signals[:6],
                    "news_unavailable": news_unavailable,
                    "news_items": news_display,
                    "explanation": f"Established quality company exhibiting technical setup: {setup}.",
                    "portfolio_context": {
                        "allocation_pct": allocation_pct,
                        "unrealized_gain_pct": unrealized_gain_pct,
                        "current_value": current_value,
                        "quantity": quantity,
                        "avg_price": avg_price,
                    },
                    "last_updated": __import__("datetime").datetime.utcnow().isoformat(),
                    "sector": h.get("sector", "Unknown"),
                    "current_price": current_price,
                    "data_status": "success" if hist_age_hours and hist_age_hours < 24 else "stale" if hist_age_hours else "unknown",
                    "data_age_hours": hist_age_hours,
                    "setup_age_hours": round((pd.Timestamp.utcnow() - pd.Timestamp(__import__("datetime").datetime.utcnow())).total_seconds() / 3600, 1) if False else 0,
                }
            except Exception as e:
                logger.warning(f"Trading analysis failed for {symbol}: {e}")
                return None

        # Enforce total scan deadline — don't let qualification run past MAX_SCAN_SECONDS
        elapsed_so_far = time.time() - scan_start
        remaining = max(10, MAX_SCAN_SECONDS - elapsed_so_far)
        logger.info(
            f"TRADING_SCAN_QUALIFY: {len(candidates)} candidates, "
            f"{elapsed_so_far:.1f}s elapsed, {remaining:.0f}s remaining budget"
        )
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[_qualify(*c) for c in candidates],
                    return_exceptions=True,
                ),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"TRADING_SCAN_TIMEOUT: qualification exceeded {remaining:.0f}s budget "
                f"({len(candidates)} candidates). Returning partial results."
            )
            results = []

        # Filter out None (filtered) and exceptions (failed)
        opportunities = []
        failed_qualifications = 0
        for r in results:
            if isinstance(r, Exception):
                failed_qualifications += 1
                logger.warning(f"Trading qualification raised: {r}")
            elif r is not None:
                opportunities.append(r)

        # ── Add source labels + is_portfolio_holding ──────────────
        for opp in opportunities:
            sym = opp["symbol"]
            is_portfolio = sym in portfolio_symbols
            opp["is_portfolio_holding"] = is_portfolio
            if universe == "selected":
                opp["source"] = "Selected"
            elif universe == "watchlist":
                opp["source"] = "Watchlist"
            elif universe == "portfolio_watchlist":
                opp["source"] = "Portfolio + Watchlist" if is_portfolio else "Watchlist"
            else:
                opp["source"] = "Portfolio"

        scan_duration = time.time() - scan_start
        logger.info(
            f"Trading scan complete: {len(opportunities)} opportunities from "
            f"{len(candidates)} candidates ({failed_qualifications} failed) "
            f"in {scan_duration:.1f}s"
        )

        # ── Near-miss candidates (scored but didn't qualify) ──────
        # Holdings that had historical data but no strong setup — show as "closest"
        near_misses = []
        for h in eligible:
            sym = h["symbol"]
            if any(o["symbol"] == sym for o in opportunities):
                continue  # Already in opportunities
            rows = hist_rows.get(sym) or []
            if len(rows) < 60:
                continue
            df_near = pd.DataFrame(rows)
            if "close" not in df_near.columns:
                continue
            df_near.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume"
            }, inplace=True)
            try:
                price_val = float(df_near["Close"].iloc[-1])
                tech = self.technical_engine.analyze(df_near, price_val)
                # Simple near-miss score: trend strength + momentum
                nm_score = tech.get("trend_strength", 30)
                if tech.get("momentum") in ("Bullish", "Strong Bullish"):
                    nm_score += 10
                elif tech.get("momentum") in ("Bearish", "Strong Bearish"):
                    nm_score -= 10
                near_misses.append({
                    "symbol": sym,
                    "name": h.get("name", sym),
                    "score": round(min(100, max(0, nm_score)), 1),
                    "trend": tech.get("trend", "Neutral"),
                    "momentum": tech.get("momentum", "Neutral"),
                    "sector": h.get("sector", "Unknown"),
                })
            except Exception:
                pass
        near_misses.sort(key=lambda x: x["score"], reverse=True)
        near_misses = near_misses[:5]

        # ── Portfolio swap recommendations (only when scanning portfolio) ──
        swap_recommendations = []
        if universe == "portfolio":
            swap_recommendations = self._generate_swap_recommendations(all_holdings, hist_rows)

        # ── Rank and cap ────────────────────────────────────
        opportunities.sort(key=lambda x: x.get("rank_score", 0), reverse=True)
        max_opps = 10
        opportunities = opportunities[:max_opps]

        for i, opp in enumerate(opportunities):
            opp["display_rank"] = i + 1

        # Determine data_status — distinguish real failures from stale usage
        if total_eligible == 0:
            data_status = "success"
        elif symbols_with_data == total_eligible:
            data_status = "success"
        elif symbols_with_data > 0:
            data_status = "partial"
        elif data_source == "provider_unavailable":
            data_status = "provider_unavailable"
        elif symbols_failed:
            data_status = "provider_unavailable"
        else:
            data_status = "success"

        result = {
            "opportunities": opportunities,
            "near_misses": near_misses,
            "swap_recommendations": swap_recommendations,
            "universe": universe,
            "scanned_count": len(all_holdings),
            "data_status": data_status,
            "data_source": data_source,
            "data_quality": {
                "total_holdings": len(all_holdings),
                "eligible_holdings": total_eligible,
                "holdings_with_data": symbols_with_data,
                "failed_symbols": symbols_failed,
                "candidates_found": len(candidates),
                "opportunities_found": len(opportunities),
                "qualifications_failed": failed_qualifications,
                "near_miss_count": len(near_misses),
                "swap_count": len(swap_recommendations),
                "scan_duration_seconds": round(scan_duration, 1),
                "data_source": data_source,
                "stale_age": stale_age,
            },
        }
        return result

    def _classify_maturity(self, technical, signals, trend, setup) -> str:
        """Classify setup maturity: EARLY / DEVELOPING / CONFIRMED / MATURE / EXTENDED."""
        strength = technical.get("trend_strength", 50)
        momentum = technical.get("momentum", "Neutral")
        indicators = technical.get("indicators", {})

        # Extended: price way above moving averages + overbought
        rsi = indicators.get("rsi")
        if rsi and rsi > 75:
            return "EXTENDED"
        if strength > 80 and "Above Upper Bollinger" in signals:
            return "EXTENDED"

        # Confirmed: multiple confirming signals
        confirming = sum(1 for s in signals if s in (
            "Golden Cross Active", "RSI Oversold", "Above Upper Bollinger",
            "MACD Bullish", "SMA Trending Up",
        ))
        if confirming >= 2:
            return "CONFIRMED"

        # Mature: single signal with strong trend
        if momentum in ("Bullish", "Bearish") and strength > 65:
            return "MATURE"

        # Developing: signal present, trend forming
        if setup and strength > 40:
            return "DEVELOPING"

        return "EARLY"

    def _classify_validity(self, setup, trend) -> str:
        """Classify setup validity: FRESH / VALID / AGING / STALE / INVALIDATED."""
        if not setup:
            return "INVALIDATED"

        # Fresh: just triggered (setup + trend alignment)
        if "Pullback" in (setup or "") and trend in ("Uptrend", "Strong Uptrend"):
            return "FRESH"
        if "Golden Cross" in (setup or ""):
            return "FRESH"

        # Valid: setup still intact
        if trend in ("Uptrend", "Strong Uptrend", "Neutral"):
            return "VALID"

        # Aging: trend weakening
        if trend == "Neutral":
            return "AGING"

        # Invalidated: trend has reversed against setup
        return "INVALIDATED"

    def _generate_why_now(self, setup, signals, technical, trend) -> Dict[str, str]:
        """Generate 'Why Now?' explanation."""
        reasons = []

        if "Pullback in Uptrend" in (setup or ""):
            reasons.append("RSI oversold condition in an uptrend presents a buy-the-dip opportunity")
        elif "Golden Cross" in (setup or ""):
            reasons.append("50-day SMA crossing above 200-day SMA signals momentum shift")
        elif "Bollinger" in (setup or ""):
            reasons.append("Price touching upper Bollinger Band indicates potential breakout or pullback")

        if technical.get("momentum") == "Bullish":
            reasons.append("Bullish momentum supports the setup")
        if trend in ("Strong Uptrend",):
            reasons.append("Strong underlying trend provides support")

        why_now = "; ".join(reasons[:2]) if reasons else "Technical conditions align for a potential entry"
        why_not_now = self._generate_why_not_now(setup, technical, trend)

        return {"why": why_now, "why_not": why_not_now}

    def _generate_why_not_now(self, setup, technical, trend) -> str:
        """Generate 'Why Not Now?' — what would invalidate the setup."""
        concerns = []
        indicators = technical.get("indicators", {})
        rsi = indicators.get("rsi")

        if rsi and rsi > 70:
            concerns.append(f"RSI is elevated at {rsi:.0f} — wait for pullback")
        if trend in ("Downtrend", "Strong Downtrend"):
            concerns.append("Underlying trend is bearish — counter-trend trade is higher risk")
        if technical.get("trend_strength", 50) < 30:
            concerns.append("Trend strength is weak - setup may not follow through")

        return "; ".join(concerns[:2]) if concerns else "No immediate concerns - setup is actionable"

    def _score_opportunity(self, setup, technical, fundamental, trend, maturity) -> float:
        """Score opportunity 0-100 for ranking.
        
        MULTI-FACTOR MODEL — Golden Cross is ONE factor, never dominant:
        1. Trend structure (SMA alignment, ADX) — 20%
        2. Momentum (RSI, MACD) — 15%
        3. Volume confirmation — 10%
        4. Golden Cross confirmation — 10%
        5. Fundamental quality — 20%
        6. Setup type — 10%
        7. Maturity alignment — 10%
        8. Risk quality (ATR) — 5%
        """
        indicators = technical.get("indicators", {})
        score = 30  # base

        # 1. Trend structure (0-20)
        trend_strength = technical.get("trend_strength", 50)
        trend_score = min(20, trend_strength * 0.25)
        if trend in ("Strong Uptrend",):
            trend_score = min(20, trend_score + 3)
        elif trend in ("Uptrend",):
            trend_score = min(20, trend_score + 1)
        elif trend in ("Downtrend", "Strong Downtrend"):
            trend_score = max(0, trend_score - 10)
        score += trend_score

        # 2. Momentum (0-15)
        rsi = indicators.get("rsi_14", 50)
        macd_hist = indicators.get("macd_histogram", 0)
        momentum_score = 0
        if 40 <= rsi <= 60:
            momentum_score += 7  # neutral = healthy
        elif 30 <= rsi < 40:
            momentum_score += 10  # oversold in uptrend = opportunity
        elif rsi > 70:
            momentum_score += 2  # overbought = caution
        else:
            momentum_score += 5
        if macd_hist > 0:
            momentum_score += min(8, macd_hist * 100)
        score += min(15, momentum_score)

        # 3. Volume confirmation (0-10)
        vol_ratio = indicators.get("volume_ratio", 1.0)
        if vol_ratio > 1.5:
            score += min(10, vol_ratio * 3)
        elif vol_ratio > 1.0:
            score += 4
        else:
            score += 2

        # 4. Golden Cross — ONE factor, capped at 10 points (NOT dominant)
        has_golden_cross = "Golden Cross Active" in [s if isinstance(s, str) else s.get("signal", "") for s in technical.get("signals", [])]
        if has_golden_cross:
            score += 8  # meaningful but NOT dominant
        else:
            score += 2  # no penalty — setups can exist without Golden Cross

        # 5. Fundamental quality (0-20)
        f_score = fundamental.get("score", 50)
        score += (f_score / 100) * 20

        # 6. Setup type (0-10)
        if "Pullback" in (setup or ""):
            score += 8  # pullback in uptrend is classic swing
        elif "Golden Cross" in (setup or ""):
            score += 6
        elif "Bollinger" in (setup or ""):
            score += 5
        elif "MACD" in (setup or ""):
            score += 5
        elif "Support" in (setup or ""):
            score += 6
        elif "Volume" in (setup or ""):
            score += 4
        else:
            score += 3

        # 7. Maturity alignment (0-10)
        maturity_bonus = {
            "EARLY": 3,
            "DEVELOPING": 6,
            "CONFIRMED": 10,
            "MATURE": 8,
            "EXTENDED": 2,
        }
        score += maturity_bonus.get(maturity, 5)

        # 8. Risk quality (0-5) — use ATR/price ratio if available
        atr = indicators.get("atr_14", 0)
        sma_20 = indicators.get("sma_20", 0) or indicators.get("sma_50", 0) or 100
        atr_pct = (atr / sma_20 * 100) if atr and sma_20 else 0
        if 1.0 <= atr_pct <= 3.0:
            score += 5  # ideal volatility
        elif atr_pct < 1.0:
            score += 3  # low vol = slow moves
        elif atr_pct > 0:
            score += 2  # high vol = risky

        return max(0, min(100, round(score, 1)))

    def _estimate_horizon(self, setup: str, trend: str, momentum: str, atr, current_price: float) -> str:
        """Estimate trade horizon from technical conditions."""
        if not current_price:
            return "1-4 weeks"

        # ATR-based: if ATR is large relative to price, shorter horizon
        atr_pct = (atr / current_price * 100) if atr and current_price else 0

        if "Golden Cross" in (setup or ""):
            if trend in ("Strong Uptrend",) and momentum == "Bullish":
                return "1-4 weeks"
            return "3-10 days"
        if "Pullback" in (setup or ""):
            if atr_pct > 3:
                return "1-3 days"
            return "3-10 days"
        if "Bollinger" in (setup or ""):
            return "1-3 days"

        # Default based on trend strength
        if trend in ("Strong Uptrend",):
            return "1-4 weeks"
        if trend in ("Uptrend",):
            return "3-10 days"
        return "1-3 days"

    def _compute_late_entry_pct(self, setup: str, technical: dict, current_price: float) -> Optional[float]:
        """Compute how far price has moved from ideal entry (0% = perfect entry)."""
        if not current_price:
            return None
        indicators = technical.get("indicators", {})
        signals = technical.get("signals", [])

        try:
            signal_names = [s if isinstance(s, str) else s.get("signal", "") for s in signals]
            if "RSI Oversold" in signal_names:
                support = technical.get("support_levels", [])
                if support and support[0] > 0:
                    return round((current_price - support[0]) / support[0] * 100, 1)

            if "Golden Cross Active" in signal_names:
                sma_50 = indicators.get("sma_50")
                if sma_50 and sma_50 > 0:
                    return round((current_price - sma_50) / sma_50 * 100, 1)

            if "Above Upper Bollinger" in signal_names:
                return round(2.0, 1)
        except Exception:
            pass
        return None

    def _compute_entry_status(self, late_entry_pct: Optional[float], trend: str, maturity: str) -> str:
        """Determine if entry is still actionable or has been missed.
        
        Returns: ACTIONABLE / EXTENDED / ENTRY_MISSED / WAIT_FOR_PULLBACK / INVALIDATED
        """
        if late_entry_pct is None:
            return "ACTIONABLE"

        if late_entry_pct > 8:
            return "ENTRY_MISSED"
        elif late_entry_pct > 5:
            return "WAIT_FOR_PULLBACK"
        elif late_entry_pct > 3:
            return "EXTENDED"
        elif maturity == "EXTENDED":
            return "EXTENDED"
        elif trend in ("Downtrend", "Strong Downtrend"):
            return "INVALIDATED"
        else:
            return "ACTIONABLE"

    def _classify_freshness(self, maturity: str, entry_status: str, late_entry_pct: Optional[float], trend: str) -> str:
        """Classify setup freshness: Fresh / Aging / Stale / Invalidated."""
        if entry_status == "INVALIDATED" or trend in ("Downtrend", "Strong Downtrend"):
            return "Invalidated"
        if late_entry_pct is not None and late_entry_pct > 8:
            return "Stale"
        if late_entry_pct is not None and late_entry_pct > 5:
            return "Aging"
        if maturity == "EXTENDED":
            return "Aging"
        if maturity in ("CONFIRMED", "MATURE"):
            return "Fresh"
        if maturity == "DEVELOPING":
            return "Fresh"
        return "Aging"

    def _compute_score_breakdown(self, technical, fundamental, trend, maturity, setup, indicators) -> Dict[str, Any]:
        """Compute score breakdown components for 'Why this score?' display."""
        trend_strength = technical.get("trend_strength", 50)
        rsi = indicators.get("rsi_14", 50)
        macd_hist = indicators.get("macd_histogram", 0)
        vol_ratio = indicators.get("volume_ratio", 1.0)
        f_score = fundamental.get("score", 50)

        has_gc = "Golden Cross Active" in [s if isinstance(s, str) else s.get("signal", "") for s in technical.get("signals", [])]

        trend_pts = min(20, round(trend_strength * 0.25 + (3 if trend == "Strong Uptrend" else 1 if trend == "Uptrend" else -10 if "Down" in trend else 0), 1))
        trend_pts = max(0, min(20, trend_pts))

        mom_pts = 0
        if 40 <= rsi <= 60: mom_pts = 7
        elif 30 <= rsi < 40: mom_pts = 10
        elif rsi > 70: mom_pts = 2
        else: mom_pts = 5
        if macd_hist > 0: mom_pts += min(8, round(macd_hist * 100, 1))
        mom_pts = max(0, min(15, mom_pts))

        vol_pts = min(10, round(vol_ratio * 3, 1)) if vol_ratio > 1.5 else 4 if vol_ratio > 1.0 else 2

        gc_pts = 8 if has_gc else 2

        fund_pts = round((f_score / 100) * 20, 1)

        setup_pts_map = {"Pullback": 8, "Golden Cross": 6, "Bollinger": 5, "MACD": 5, "Support": 6, "Volume": 4}
        setup_pts = 3
        for key, pts in setup_pts_map.items():
            if key in (setup or ""):
                setup_pts = pts
                break

        mat_map = {"EARLY": 3, "DEVELOPING": 6, "CONFIRMED": 10, "MATURE": 8, "EXTENDED": 2}
        mat_pts = mat_map.get(maturity, 5)

        atr = indicators.get("atr_14", 0)
        sma20 = indicators.get("sma_20", 0) or indicators.get("sma_50", 0) or 100
        atr_pct = (atr / sma20 * 100) if atr and sma20 else 0
        risk_pts = 5 if 1.0 <= atr_pct <= 3.0 else 3 if atr_pct < 1.0 else 2 if atr_pct > 0 else 0

        return {
            "trend": {"score": trend_pts, "max": 20, "label": "Trend"},
            "momentum": {"score": mom_pts, "max": 15, "label": "Momentum"},
            "volume": {"score": vol_pts, "max": 10, "label": "Volume"},
            "golden_cross": {"score": gc_pts, "max": 10, "label": "Golden Cross"},
            "fundamental": {"score": fund_pts, "max": 20, "label": "Fundamentals"},
            "setup_type": {"score": setup_pts, "max": 10, "label": "Setup Type"},
            "maturity": {"score": mat_pts, "max": 10, "label": "Maturity"},
            "risk_quality": {"score": risk_pts, "max": 5, "label": "Risk Quality"},
        }

    async def get_long_term_opportunities(self, force: bool = False) -> Dict[str, Any]:
        """
        Long-term investment opportunities based on fundamental quality.
        Separate from swing trading — focused on earnings, growth, valuation, quality.
        """
        cache_key = "long_term_opportunities"
        if not force:
            cached = _get_cached_result(cache_key)
            if cached is not None:
                return cached

        holdings = self.portfolio_service.get_holdings()
        symbols = [h["symbol"] for h in holdings]
        holding_map = {h["symbol"]: h for h in holdings}

        opportunities = []
        for symbol in symbols:
            try:
                info = await asyncio.wait_for(
                    self.stock_service.get_stock_info(symbol),
                    timeout=20,
                )
                if not info or info.get("error"):
                    continue

                metrics = {
                    "pe_ratio": info.get("pe_ratio"),
                    "forward_pe": info.get("forward_pe"),
                    "peg_ratio": info.get("peg_ratio"),
                    "price_to_book": info.get("price_to_book"),
                    "price_to_sales": info.get("price_to_sales"),
                    "ev_to_ebitda": info.get("ev_to_ebitda"),
                    "profit_margin": info.get("profit_margin"),
                    "operating_margin": info.get("operating_margin"),
                    "gross_margin": info.get("gross_margin"),
                    "revenue": info.get("revenue"),
                    "revenue_growth": info.get("revenue_growth"),
                    "earnings": info.get("earnings"),
                    "eps": info.get("eps"),
                    "dividend_yield": info.get("dividend_yield"),
                    "roe": info.get("roe"),
                    "debt_to_equity": info.get("debt_to_equity"),
                    "free_cash_flow": info.get("free_cash_flow"),
                }
                fundamental = self.fundamental_engine.analyze(metrics)
                h = holding_map.get(symbol, {})

                # Long-term score: heavily weighted on fundamentals
                lt_score = fundamental.get("score", 50)
                f_strengths = fundamental.get("strengths", [])
                f_weaknesses = fundamental.get("weaknesses", [])

                # Determine action
                if lt_score >= 75 and len(f_weaknesses) <= 1:
                    action = "ADD"
                elif lt_score >= 60:
                    action = "HOLD"
                elif lt_score >= 45:
                    action = "WATCH"
                elif lt_score >= 30:
                    action = "REDUCE"
                else:
                    action = "SELL"

                opportunities.append({
                    "symbol": symbol,
                    "name": h.get("name") or info.get("name"),
                    "sector": h.get("sector", info.get("sector", "Unknown")),
                    "current_price": h.get("current_price", 0),
                    "current_value": h.get("current_value", 0),
                    "unrealized_gain_pct": h.get("unrealized_gain_pct", 0),
                    "allocation_pct": h.get("allocation_pct", 0),
                    "fundamental_score": lt_score,
                    "fundamental_grade": fundamental.get("grade", "N/A"),
                    "strengths": f_strengths,
                    "weaknesses": f_weaknesses,
                    "metrics": metrics,
                    "action": action,
                    "recommendation": fundamental.get("explanation", ""),
                })
            except Exception as e:
                logger.warning(f"Long-term analysis failed for {symbol}: {e}")
                continue

        # Sort by fundamental score
        opportunities.sort(key=lambda x: x.get("fundamental_score", 0), reverse=True)

        result = {
            "opportunities": opportunities,
            "data_status": "success" if opportunities else "partial",
            "total_holdings": len(holdings),
            "analyzed": len(opportunities),
            "last_updated": __import__("datetime").datetime.utcnow().isoformat(),
        }
        _set_cached_result(cache_key, result)
        return result

    def _generate_swap_recommendations(
        self, holdings: List[Dict[str, Any]], hist_rows: Dict[str, list]
    ) -> List[Dict[str, Any]]:
        """
        Generate portfolio stock-swap recommendations.
        Identifies holdings that may need attention and suggests replacements.
        
        Uses the existing RebalancingEngine's candidate universe and
        evaluates fundamental quality + diversification benefit.
        """
        from app.engines.rebalancing import RebalancingEngine, CANDIDATE_UNIVERSE

        if not holdings or len(holdings) < 3:
            return []

        engine = RebalancingEngine()
        total_value = sum(h.get("current_value", 0) or 0 for h in holdings)
        if total_value <= 0:
            return []

        # Build sector allocation
        sector_alloc = {}
        for h in holdings:
            sector = h.get("sector", "Unknown") or "Unknown"
            val = h.get("current_value", 0) or 0
            pct = (val / total_value * 100) if total_value > 0 else 0
            sector_alloc[sector] = sector_alloc.get(sector, 0) + pct

        holding_symbols = {h["symbol"] for h in holdings}
        swaps = []

        for h in holdings:
            symbol = h["symbol"]
            sector = h.get("sector", "Unknown") or "Unknown"
            gain_pct = h.get("unrealized_gain_pct") or 0
            alloc_pct = (h.get("current_value", 0) or 0) / total_value * 100 if total_value else 0

            # Flag conditions that suggest reviewing a holding
            flags = []
            if gain_pct < -15:
                flags.append({"type": "underperformance", "severity": "high",
                              "detail": f"Down {abs(gain_pct):.1f}%"})
            if alloc_pct > 15:
                flags.append({"type": "overconcentration", "severity": "medium",
                              "detail": f"Position is {alloc_pct:.1f}% of portfolio"})
            sector_pct = sector_alloc.get(sector, 0)
            if sector_pct > 25:
                peers = [h2 for h2 in holdings if h2.get("sector") == sector and h2["symbol"] != symbol]
                peer_avg = sum((h2.get("unrealized_gain_pct") or 0) for h2 in peers) / len(peers) if peers else 0
                if gain_pct < peer_avg - 10:
                    flags.append({"type": "sector_underperformance", "severity": "medium",
                                  "detail": f"Underperforming {sector} peers"})

            if not flags:
                continue

            # Determine action
            high_count = sum(1 for f in flags if f["severity"] == "high")
            if high_count >= 1:
                action = "REDUCE"
            else:
                action = "REVIEW"

            # Find best replacement from candidate universe
            sector_is_overweight = sector_pct > 20
            best_candidate = None
            best_score = 0

            excluded = holding_symbols | {symbol}
            for candidate in CANDIDATE_UNIVERSE.get(sector, []):
                ticker = candidate["ticker"]
                if ticker in excluded:
                    continue
                score = candidate.get("quality", 75)
                if sector_is_overweight:
                    score += 5  # same sector but sector is overweight — less ideal
                if score > best_score:
                    best_score = score
                    best_candidate = candidate

            if best_candidate and best_score >= 60:
                # Calculate improvement
                source_fundamental_score = 50  # baseline when unknown
                try:
                    source_info = None
                    # Try to get cached info for the source
                    cached = self.stock_service.cache.get_cached_stock_info_any_age(symbol)
                    if cached and not cached.get("error"):
                        source_metrics = {k: cached.get(k) for k in [
                            "pe_ratio", "profit_margin", "roe", "debt_to_equity", "revenue_growth"]}
                        src_fund = self.fundamental_engine.analyze(source_metrics)
                        source_fundamental_score = src_fund.get("score", 50)
                except Exception:
                    pass

                improvement = best_score - source_fundamental_score

                swaps.append({
                    "source_holding": symbol,
                    "source_name": h.get("name", symbol),
                    "source_sector": sector,
                    "source_unrealized_gain_pct": round(gain_pct, 1),
                    "source_allocation_pct": round(alloc_pct, 1),
                    "replacement_symbol": best_candidate["ticker"],
                    "replacement_name": best_candidate["name"],
                    "replacement_sector": sector,
                    "replacement_score": best_score,
                    "source_score": round(source_fundamental_score, 1),
                    "improvement_score": round(improvement, 1),
                    "action": action,
                    "confidence": "High" if high_count >= 1 else "Medium",
                    "fundamental_reason": f"Replacement quality score {best_score}/100 vs current {source_fundamental_score}/100",
                    "diversification_reason": f"Maintains {sector} exposure" if not sector_is_overweight else f"Same sector — {sector} is overweight at {sector_pct:.1f}%",
                    "portfolio_impact": f"Reduces {sector} concentration" if sector_is_overweight else "Maintains sector allocation",
                    "flags": flags,
                    "data_status": "success",
                })

        swaps.sort(key=lambda s: (
            0 if s["action"] == "REDUCE" else 1,
            -s["improvement_score"]
        ))
        return swaps[:5]
