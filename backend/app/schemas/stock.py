"""Stock and analysis Pydantic schemas."""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


# ── Stock Info ───────────────────────────────────────────

class StockPrice(BaseModel):
    symbol: str
    price: float
    previous_close: Optional[float] = None
    open: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[float] = None
    avg_volume: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    market_cap: Optional[float] = None
    cached_at: Optional[datetime] = None

class StockInfoResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    asset_type: Optional[str] = None
    exchange: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    employees: Optional[int] = None
    country: Optional[str] = None
    price: Optional[StockPrice] = None
    cached_at: Optional[datetime] = None


# ── Fundamental Analysis ─────────────────────────────────

class FundamentalMetrics(BaseModel):
    # Revenue & Growth
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    # Earnings
    earnings: Optional[float] = None
    eps: Optional[float] = None
    eps_growth: Optional[float] = None
    # Margins
    profit_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    gross_margin: Optional[float] = None
    # Cash & Debt
    free_cash_flow: Optional[float] = None
    cash: Optional[float] = None
    total_debt: Optional[float] = None
    debt_to_equity: Optional[float] = None
    # Returns
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None
    # Valuation
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_sales: Optional[float] = None
    price_to_book: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    # Dividends
    dividend_yield: Optional[float] = None
    dividend_rate: Optional[float] = None
    payout_ratio: Optional[float] = None
    ex_dividend_date: Optional[str] = None
    # Other
    beta: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None

class FundamentalAnalysis(BaseModel):
    symbol: str
    metrics: FundamentalMetrics
    score: float = 0.0  # 0-100
    grade: str = "Insufficient Data"  # Strong, Healthy, Mixed, Weak, Insufficient Data
    strengths: List[str] = []
    weaknesses: List[str] = []
    explanation: str = ""
    cached_at: Optional[datetime] = None


# ── Technical Analysis ───────────────────────────────────

class TechnicalIndicators(BaseModel):
    # Moving Averages
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    # Oscillators
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    # Bollinger Bands
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    # Volatility & Trend
    atr_14: Optional[float] = None
    adx_14: Optional[float] = None
    # Volume
    volume: Optional[float] = None
    avg_volume_20: Optional[float] = None
    volume_ratio: Optional[float] = None
    # Support/Resistance
    support: Optional[float] = None
    resistance: Optional[float] = None

class TechnicalAnalysis(BaseModel):
    symbol: str
    current_price: float = 0.0
    indicators: TechnicalIndicators
    trend: str = "Neutral"  # Strong Uptrend, Uptrend, Neutral, Downtrend, Strong Downtrend
    trend_strength: float = 0.0  # 0-100
    momentum: str = "Neutral"  # Strong Bullish, Bullish, Neutral, Bearish, Strong Bearish
    signals: List[Dict[str, Any]] = []  # [{signal, type, description}]
    support_levels: List[float] = []
    resistance_levels: List[float] = []
    historical_data: List[Dict[str, Any]] = []  # OHLCV for charting
    explanation: str = ""
    cached_at: Optional[datetime] = None


# ── Risk Analysis ────────────────────────────────────────

class StockRisk(BaseModel):
    symbol: str
    volatility: Optional[float] = None  # Annualized
    beta: Optional[float] = None
    max_drawdown: Optional[float] = None
    var_95: Optional[float] = None  # Value at Risk 95%
    downside_deviation: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    risk_score: float = 50.0  # 0-100
    risk_level: str = "Moderate"  # Low, Moderate, Elevated, High

class PortfolioRisk(BaseModel):
    risk_score: float = 50.0
    risk_level: str = "Moderate"
    portfolio_volatility: Optional[float] = None
    portfolio_beta: Optional[float] = None
    portfolio_var_95: Optional[float] = None
    max_drawdown: Optional[float] = None
    concentration_risk: Optional[float] = None
    sector_concentration: Optional[float] = None
    correlation_risk: Optional[float] = None
    contributors: List[Dict[str, Any]] = []
    explanation: str = ""


# ── Diversification ──────────────────────────────────────

class DiversificationAnalysis(BaseModel):
    score: float = 50.0  # 0-100
    level: str = "Moderate"  # Excellent, Good, Moderate, Poor, Critical
    position_concentration: Dict[str, float] = {}
    sector_allocation: Dict[str, float] = {}
    asset_type_allocation: Dict[str, float] = {}
    high_concentration_positions: List[Dict[str, Any]] = []
    correlated_pairs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    recommendations: List[str] = []
    explanation: str = ""


# ── Recommendation ───────────────────────────────────────

class Recommendation(BaseModel):
    symbol: str
    action: str = "INSUFFICIENT DATA"
    # HOLD, WATCH, CONSIDER BUY, TAKE PROFIT, REDUCE, SELL, AVOID, INSUFFICIENT DATA
    confidence: str = "Low"  # Low, Medium, High, Strong
    score: float = 50.0  # 0-100
    reasons: List[str] = []
    positive_factors: List[str] = []
    negative_factors: List[str] = []
    risks: List[str] = []
    what_would_change: List[str] = []
    fundamental_input: Optional[float] = None
    technical_input: Optional[float] = None
    sentiment_input: Optional[float] = None
    risk_input: Optional[float] = None
    explanation: str = ""
    cached_at: Optional[datetime] = None


# ── News & Sentiment ─────────────────────────────────────

class NewsItem(BaseModel):
    title: str
    summary: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    symbol: Optional[str] = None
    sentiment: Optional[str] = None  # positive, neutral, negative
    sentiment_score: Optional[float] = None
    impact: Optional[str] = None  # low, medium, high
    category: Optional[str] = None

class SentimentSummary(BaseModel):
    symbol: str
    overall_sentiment: str = "Neutral"
    sentiment_score: float = 0.0
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0
    recent_articles: List[NewsItem] = []
    explanation: str = ""


# ── Catalyst ─────────────────────────────────────────────

class Catalyst(BaseModel):
    symbol: Optional[str] = None
    event_type: str  # earnings, dividend, fda, merger, contract, etc.
    title: str
    description: Optional[str] = None
    date: Optional[datetime] = None
    impact: str = "medium"  # low, medium, high
    sentiment: str = "neutral"


# ── Backtest ─────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str  # sma_crossover, rsi_reversal, macd_signal, custom
    params: Dict[str, Any] = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000.0

class BacktestResult(BaseModel):
    symbol: str
    strategy: str
    total_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    profit_loss: float = 0.0
    sharpe_ratio: Optional[float] = None
    benchmark_return: Optional[float] = None
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    assumptions: List[str] = []


# ── Portfolio Health ─────────────────────────────────────

class PortfolioHealthReport(BaseModel):
    overall_score: float = 50.0
    risk_assessment: str = ""
    diversification_assessment: str = ""
    performance_assessment: str = ""
    strong_holdings: List[Dict[str, Any]] = []
    weak_holdings: List[Dict[str, Any]] = []
    important_news: List[NewsItem] = []
    fundamental_concerns: List[str] = []
    concentration_risks: List[str] = []
    opportunities: List[str] = []
    items_to_monitor: List[str] = []
    full_report: str = ""
    generated_at: datetime = datetime.utcnow()


# ── Trading Opportunities ───────────────────────────────

class TradingOpportunity(BaseModel):
    symbol: str
    name: Optional[str] = None
    setup: str = ""
    trend: str = "Neutral"
    catalyst: Optional[str] = None
    sentiment: Optional[str] = None
    risk: str = "Medium"
    potential_upside: Optional[float] = None
    potential_downside: Optional[float] = None
    technical_factors: List[str] = []
    explanation: str = ""
    market_cap: Optional[float] = None
    volume: Optional[float] = None
