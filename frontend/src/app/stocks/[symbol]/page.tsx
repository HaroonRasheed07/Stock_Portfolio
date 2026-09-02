"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { fetchAPI } from "@/lib/api";
import { formatCurrency, formatPercent, formatNumber } from "@/lib/utils";
import { StockChart } from "@/components/charts/StockChart";
import {
  Building, TrendingUp, ShieldAlert, Sparkles, Newspaper,
  FileText, Activity, AlertTriangle, CheckCircle, BarChart2,
  ExternalLink, Calendar, ShieldCheck, Clock, Zap
} from "lucide-react";

const IMPACT_STYLES: Record<string, string> = {
  CRITICAL: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  HIGH: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  MEDIUM: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  LOW: "bg-slate-800 text-slate-400 border-slate-700",
};

const SENTIMENT_STYLES: Record<string, string> = {
  positive: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  negative: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  neutral: "bg-slate-800 text-slate-400 border-slate-700",
};

function formatAssetType(raw?: string | null): string {
  if (!raw) return "Stock";
  const t = raw.toUpperCase();
  if (t === "ETF" || t === "FUND") return "ETF";
  if (t === "REIT") return "REIT";
  if (t === "EQUITY" || t === "STOCK") return "Stock";
  return raw;
}

function metricNA(label: string, isETF: boolean): string {
  if (isETF) return "N/A — ETF";
  return "Not available";
}

function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Date unavailable";
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (isNaN(then)) return "Date unavailable";
  const diffMs = now - then;
  if (diffMs < 0) return "Just now";
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

export default function StockDetailPage() {
  const params = useParams();
  const symbol = (params.symbol as string)?.toUpperCase();
  const [analysis, setAnalysis] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(true);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");
  const [expandedTimeline, setExpandedTimeline] = useState<number | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);

    // Load analysis + catalysts first (fast path shows the page)
    Promise.allSettled([
      fetchAPI<any>(`/stocks/${symbol}/analysis`),
      fetchAPI<any[]>(`/catalysts/timeline/${symbol}?limit=20`).catch(() => []),
    ])
      .then(([aResult, tResult]) => {
        if (!mountedRef.current) return;
        const aData = aResult.status === "fulfilled" ? aResult.value : null;
        const tData = tResult.status === "fulfilled" ? tResult.value : [];
        setAnalysis(aData);
        setTimeline(tData || []);
        setLoading(false);

        // Load chart independently — yfinance can be slow on cold cache
        setChartLoading(true);
        fetchAPI<any[]>(`/stocks/${symbol}/history?period=1y`)
          .then((hData) => {
            if (mountedRef.current && hData && hData.length > 0) {
              setHistory(hData);
            }
          })
          .catch(() => {})
          .finally(() => { if (mountedRef.current) setChartLoading(false); });
      })
      .catch((err) => { console.error(err); setLoading(false); });
  }, [symbol]);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6">
          <div className="h-8 w-32 bg-slate-800 rounded mb-3"></div>
          <div className="h-4 w-64 bg-slate-800 rounded"></div>
        </div>
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl h-[350px]"></div>
        <div className="grid grid-cols-3 gap-6">
          {[1,2,3].map(i => <div key={i} className="bg-[#121824] border border-[#1e293b] rounded-xl h-32"></div>)}
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="p-6 bg-[#121824] border border-[#1e293b] rounded-xl text-center">
        <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-2" />
        <h2 className="text-base font-bold text-amber-200">{symbol} Not Available</h2>
        <p className="text-xs text-slate-400 mt-1">
          No market data found for <span className="text-slate-300 font-medium">{symbol}</span>.
          This ticker may be delisted, invalid, or data is temporarily unavailable.
        </p>
        <p className="text-xs text-slate-500 mt-2">Try searching for a well-known US stock like AAPL, MSFT, or GOOGL.</p>
      </div>
    );
  }

  const { overview, fundamental, technical, risk, sentiment, catalysts, recommendation, ml_prediction, news } = analysis;

  const assetType = formatAssetType(overview?.asset_type);
  const isETF = assetType === "ETF";
  const price = overview?.price?.price;
  const changePct = overview?.price?.change_pct;
  const priceDataStatus = overview?.data_status || overview?.price?.status || "success";
  const priceUnavailable = !price || price === 0 || priceDataStatus === "unavailable" || priceDataStatus === "not_found";

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "fundamentals", label: "Fundamentals" },
    { id: "technical", label: "Technical" },
    { id: "risk", label: "Risk" },
    { id: "recommendation", label: "AI Recommendation" },
    { id: "timeline", label: "Catalysts" },
    { id: "news", label: "News" },
  ];

  const formatDividendYield = (val: number | null | undefined) => {
    if (val === null || val === undefined) return metricNA("Dividend Yield", isETF);
    const pct = val < 1 ? val * 100 : val;
    return `${pct.toFixed(2)}%`;
  };

  return (
    <div className="space-y-6">
      {/* ── Stock Header ── */}
      <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-3">
              <h1 className="text-3xl font-extrabold text-slate-100">{symbol}</h1>
              <span className="text-[11px] font-semibold uppercase px-2 py-0.5 rounded-full border border-[#1e293b] text-slate-400 bg-[#0a0d14]">
                {assetType}
              </span>
              {overview?.sector && (
                <span className="text-[11px] text-slate-500">{overview.sector}</span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-lg">{overview?.name || ""}</p>
          </div>

          <div className="flex items-center gap-6">
            <div>
              <p className="text-[11px] text-slate-400 uppercase font-semibold">Price</p>
              {priceUnavailable ? (
                <p className="text-2xl font-bold text-amber-400">Data unavailable</p>
              ) : (
                <p className="text-2xl font-bold text-slate-100">{formatCurrency(price)}</p>
              )}
            </div>
            {changePct != null && !priceUnavailable && (
              <div>
                <p className="text-[11px] text-slate-400 uppercase font-semibold">Today</p>
                <p className={`text-lg font-bold ${changePct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Quick investment snapshot */}
        <div className="mt-4 pt-4 border-t border-[#1e293b] grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p className="text-[11px] text-slate-400 uppercase font-semibold">Recommendation</p>
            <p className="text-sm font-bold text-sky-400 mt-0.5">{recommendation?.recommendation || recommendation?.action || "—"}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400 uppercase font-semibold">Score</p>
            <p className="text-sm font-bold text-slate-200 mt-0.5">{recommendation?.score != null ? `${recommendation.score}/100` : "—"}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400 uppercase font-semibold">Confidence</p>
            <p className="text-sm font-bold text-slate-200 mt-0.5">{recommendation?.confidence || "—"}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400 uppercase font-semibold">Risk Level</p>
            <p className={`text-sm font-bold mt-0.5 ${
              risk?.risk_level === "Low" ? "text-emerald-400" :
              risk?.risk_level === "Moderate" ? "text-sky-400" : "text-rose-400"
            }`}>{risk?.risk_level || "—"}</p>
          </div>
        </div>
      </div>

      {/* Data unavailable banner */}
      {priceUnavailable && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-amber-300">Market data temporarily unavailable</p>
            <p className="text-[11px] text-slate-400 mt-1">
              Live price data for {symbol} could not be retrieved. Company information and other analysis may still be available below. Try refreshing in a few minutes.
            </p>
          </div>
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="flex border-b border-[#1e293b] gap-1 overflow-x-auto pb-0 scrollbar-none">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab.id
                ? "border-sky-500 text-sky-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Overview Tab ── */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {history.length > 0 ? (
            <StockChart data={history} />
          ) : chartLoading ? (
            <div className="w-full h-[350px] rounded-xl border border-[#1e293b] bg-[#121824] flex flex-col items-center justify-center space-y-3">
              <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-xs text-slate-500">Loading chart data...</p>
            </div>
          ) : (
            <div className="w-full h-[350px] rounded-xl border border-[#1e293b] bg-[#121824] flex flex-col items-center justify-center space-y-3">
              <p className="text-xs text-slate-500">Chart data unavailable</p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                {isETF ? "Fund Metrics" : "Key Metrics"}
              </h3>
              {isETF ? (
                <div className="space-y-2.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total AUM</span>
                    <span className="text-slate-200 font-medium">{overview?.etf_data?.total_assets ? `$${formatNumber(overview.etf_data.total_assets)}` : formatNumber(overview?.market_cap) || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">NAV</span>
                    <span className="text-slate-200 font-medium">{overview?.etf_data?.nav_price ? `$${overview.etf_data.nav_price.toFixed(2)}` : formatCurrency(price)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Expense Ratio</span>
                    <span className="text-slate-200 font-medium">{overview?.etf_data?.expense_ratio != null ? `${(overview.etf_data.expense_ratio * 100).toFixed(2)}%` : "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Dividend Yield</span>
                    <span className="text-slate-200 font-medium">{formatDividendYield(overview?.key_metrics?.dividend_yield || overview?.dividend_yield)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Category</span>
                    <span className="text-slate-200 font-medium">{overview?.etf_data?.category || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Fund Family</span>
                    <span className="text-slate-200 font-medium">{overview?.etf_data?.fund_family || overview?.name || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">YTD Return</span>
                    <span className="text-slate-200 font-medium">{overview?.etf_data?.ytd_return != null ? `${(overview.etf_data.ytd_return * 100).toFixed(2)}%` : "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">5Y Avg Return</span>
                    <span className="text-slate-200 font-medium">{overview?.etf_data?.yield_5yr != null ? `${(overview.etf_data.yield_5yr * 100).toFixed(2)}%` : "N/A"}</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-2.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Market Cap</span>
                    <span className="text-slate-200 font-medium">{formatNumber(overview?.market_cap || overview?.key_metrics?.market_cap)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">P/E Ratio</span>
                    <span className="text-slate-200 font-medium">{overview?.key_metrics?.pe_ratio ? overview.key_metrics.pe_ratio.toFixed(2) : metricNA("P/E", isETF)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Dividend Yield</span>
                    <span className="text-slate-200 font-medium">{formatDividendYield(overview?.key_metrics?.dividend_yield)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Beta</span>
                    <span className="text-slate-200 font-medium">{overview?.key_metrics?.beta ? overview.key_metrics.beta.toFixed(2) : metricNA("Beta", isETF)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">EPS</span>
                    <span className="text-slate-200 font-medium">{overview?.key_metrics?.eps ? `$${overview.key_metrics.eps.toFixed(2)}` : metricNA("EPS", isETF)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Profit Margin</span>
                    <span className="text-slate-200 font-medium">{overview?.key_metrics?.profit_margin ? `${(overview.key_metrics.profit_margin * 100).toFixed(1)}%` : metricNA("Profit Margin", isETF)}</span>
                  </div>
                </div>
              )}
            </div>

            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5 md:col-span-2">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                {isETF ? "Fund Description" : "Company Description"}
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed line-clamp-6">
                {overview?.description || (isETF ? "Fund description unavailable." : "Company description unavailable.")}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Fundamentals Tab ── */}
      {activeTab === "fundamentals" && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-[#1e293b] pb-4">
            <div>
              <h3 className="text-base font-bold text-slate-100">
                {isETF ? "Fund Overview" : "Fundamental Health Assessment"}
              </h3>
              <p className="text-xs text-slate-400">
                {isETF ? "ETF structure and composition" : "Calculated score based on earnings, growth, leverage, and cash flow"}
              </p>
            </div>
            {fundamental?.grade && (
              <span className="px-4 py-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold text-sm rounded-lg">
                {fundamental.grade} Grade ({fundamental.score}/100)
              </span>
            )}
          </div>

          {fundamental?.explanation && (
            <p className="text-xs text-slate-300 leading-relaxed">{fundamental.explanation}</p>
          )}

          {!isETF && fundamental?.strengths?.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
              <div>
                <h4 className="text-xs font-bold text-emerald-400 uppercase mb-2">Key Strengths</h4>
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {fundamental.strengths.map((s: string, i: number) => (
                    <li key={i} className="flex items-center space-x-2">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="text-xs font-bold text-rose-400 uppercase mb-2">Areas of Concern</h4>
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {fundamental?.weaknesses?.length > 0 ? (
                    fundamental.weaknesses.map((w: string, i: number) => (
                      <li key={i} className="flex items-center space-x-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                        <span>{w}</span>
                      </li>
                    ))
                  ) : (
                    <li className="text-slate-500">No major concern flags.</li>
                  )}
                </ul>
              </div>
            </div>
          )}

          {isETF && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {overview?.etf_data?.total_assets != null && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">Total AUM</p>
                    <p className="text-sm font-bold text-slate-200 mt-1">$${formatNumber(overview.etf_data.total_assets)}</p>
                  </div>
                )}
                {overview?.etf_data?.expense_ratio != null && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">Expense Ratio</p>
                    <p className="text-sm font-bold text-slate-200 mt-1">{(overview.etf_data.expense_ratio * 100).toFixed(2)}%</p>
                  </div>
                )}
                {overview?.etf_data?.category && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">Category</p>
                    <p className="text-sm font-bold text-slate-200 mt-1">{overview.etf_data.category}</p>
                  </div>
                )}
                {overview?.etf_data?.nav_price != null && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">NAV</p>
                    <p className="text-sm font-bold text-slate-200 mt-1">${overview.etf_data.nav_price.toFixed(2)}</p>
                  </div>
                )}
                {overview?.key_metrics?.dividend_yield != null && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">Dividend Yield</p>
                    <p className="text-sm font-bold text-slate-200 mt-1">{(overview.key_metrics.dividend_yield * 100).toFixed(2)}%</p>
                  </div>
                )}
                {overview?.etf_data?.ytd_return != null && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">YTD Return</p>
                    <p className="text-sm font-bold text-emerald-400 mt-1">{(overview.etf_data.ytd_return * 100).toFixed(2)}%</p>
                  </div>
                )}
                {overview?.etf_data?.yield_5yr != null && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">5Y Avg Return</p>
                    <p className="text-sm font-bold text-emerald-400 mt-1">{(overview.etf_data.yield_5yr * 100).toFixed(2)}%</p>
                  </div>
                )}
                {overview?.etf_data?.fund_family && (
                  <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
                    <p className="text-[10px] text-slate-500 uppercase">Fund Family</p>
                    <p className="text-sm font-bold text-slate-200 mt-1">{overview.etf_data.fund_family}</p>
                  </div>
                )}
              </div>
              {fundamental?.explanation && (
                <p className="text-xs text-slate-300 leading-relaxed">{fundamental.explanation}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Technical Tab ── */}
      {activeTab === "technical" && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-[#1e293b] pb-4">
            <div>
              <h3 className="text-base font-bold text-slate-100">Technical Trend & Indicators</h3>
              <p className="text-xs text-slate-400">Secondary technical analysis and momentum signals</p>
            </div>
            <span className="px-3 py-1 bg-sky-500/10 text-sky-400 border border-sky-500/20 font-bold text-xs rounded-lg">
              {technical?.trend} ({technical?.momentum})
            </span>
          </div>

          {technical?.explanation && (
            <p className="text-xs text-slate-300 leading-relaxed">{technical.explanation}</p>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">RSI (14)</span>
              <p className="text-sm font-bold text-slate-200 mt-0.5">{technical?.indicators?.rsi_14?.toFixed(1) || "N/A"}</p>
            </div>
            <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">SMA 200</span>
              <p className="text-sm font-bold text-slate-200 mt-0.5">{technical?.indicators?.sma_200 ? formatCurrency(technical.indicators.sma_200) : "N/A"}</p>
            </div>
            <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Support</span>
              <p className="text-sm font-bold text-emerald-400 mt-0.5">{technical?.indicators?.support ? formatCurrency(technical.indicators.support) : "N/A"}</p>
            </div>
            <div className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Resistance</span>
              <p className="text-sm font-bold text-rose-400 mt-0.5">{technical?.indicators?.resistance ? formatCurrency(technical.indicators.resistance) : "N/A"}</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Risk Tab ── */}
      {activeTab === "risk" && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-[#1e293b] pb-4">
            <div>
              <h3 className="text-base font-bold text-slate-100">Risk Profile & Drawdown Analysis</h3>
              <p className="text-xs text-slate-400">Historical volatility, beta, and downside risk evaluation</p>
            </div>
            <span className={`px-4 py-1.5 font-bold text-sm rounded-lg border ${
              risk?.risk_level === "Low" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
              risk?.risk_level === "Moderate" ? "bg-sky-500/10 text-sky-400 border-sky-500/20" :
              "bg-rose-500/10 text-rose-400 border-rose-500/20"
            }`}>
              {risk?.risk_level || "Moderate"} Risk ({risk?.risk_score || 50}/100)
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-3.5 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Volatility</span>
              <p className="text-base font-bold text-slate-200 mt-1">{risk?.volatility ? `${(risk.volatility * 100).toFixed(1)}%` : "N/A"}</p>
            </div>
            <div className="p-3.5 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Max Drawdown</span>
              <p className="text-base font-bold text-rose-400 mt-1">{risk?.max_drawdown ? `${(risk.max_drawdown * 100).toFixed(1)}%` : "N/A"}</p>
            </div>
            <div className="p-3.5 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Value at Risk (95%)</span>
              <p className="text-base font-bold text-slate-200 mt-1">{risk?.var_95 ? `${(risk.var_95 * 100).toFixed(1)}%` : "N/A"}</p>
            </div>
            <div className="p-3.5 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Sharpe Ratio</span>
              <p className="text-base font-bold text-emerald-400 mt-1">{risk?.sharpe_ratio !== null && risk?.sharpe_ratio !== undefined ? risk.sharpe_ratio.toFixed(2) : "N/A"}</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Recommendation Tab ── */}
      {activeTab === "recommendation" && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-6">
          <div className="flex items-center space-x-3">
            <Sparkles className="w-5 h-5 text-sky-400" />
            <h3 className="text-base font-bold text-slate-100">Explainable Multi-Factor Recommendation</h3>
          </div>

          {/* Recommendation card */}
          <div className="p-5 bg-sky-500/10 border border-sky-500/20 rounded-xl space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <span className="font-extrabold text-xl text-sky-300">{recommendation?.recommendation || recommendation?.action}</span>
              <div className="flex items-center gap-4 text-xs">
                <span className="text-slate-400">Score: <strong className="text-slate-200">{recommendation?.score}/100</strong></span>
                <span className="text-slate-400">Confidence: <strong className="text-slate-200">{recommendation?.confidence} ({recommendation?.confidence_label})</strong></span>
              </div>
            </div>
            {recommendation?.explanation && (
              <p className="text-xs text-slate-300 leading-relaxed">{recommendation.explanation}</p>
            )}
          </div>

          {/* Anti-panic note */}
          {recommendation?.anti_panic_note && (
            <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl">
              <p className="text-xs text-amber-300 leading-relaxed font-medium">{recommendation.anti_panic_note}</p>
            </div>
          )}

          {/* Factor breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {recommendation?.positive_factors?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-emerald-400 uppercase">Positive Factors</h4>
                <ul className="space-y-1">
                  {recommendation.positive_factors.map((f: string, idx: number) => (
                    <li key={idx} className="text-xs text-slate-300 flex items-start space-x-2">
                      <span className="text-emerald-400 mt-0.5">+</span><span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {recommendation?.negative_factors?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-rose-400 uppercase">Negative Factors</h4>
                <ul className="space-y-1">
                  {recommendation.negative_factors.map((f: string, idx: number) => (
                    <li key={idx} className="text-xs text-slate-300 flex items-start space-x-2">
                      <span className="text-rose-400 mt-0.5">-</span><span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {recommendation?.risks?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-amber-400 uppercase">Risk Factors</h4>
                <ul className="space-y-1">
                  {recommendation.risks.map((r: string, idx: number) => (
                    <li key={idx} className="text-xs text-slate-300 flex items-start space-x-2">
                      <span className="text-amber-400 mt-0.5">!</span><span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {recommendation?.what_would_change?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-sky-400 uppercase">What Could Change This</h4>
                <ul className="space-y-1">
                  {recommendation.what_would_change.map((w: string, idx: number) => (
                    <li key={idx} className="text-xs text-slate-300 flex items-start space-x-2">
                      <span className="text-sky-400 mt-0.5">*</span><span>{w}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Score inputs */}
          <div className="border-t border-[#1e293b] pt-4 space-y-2">
            <h4 className="text-xs font-bold text-slate-400 uppercase">Score Inputs</h4>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                { label: "Fundamental", value: recommendation?.fundamental_input },
                { label: "Technical", value: recommendation?.technical_input },
                { label: "Sentiment", value: recommendation?.sentiment_input },
                { label: "Risk", value: recommendation?.risk_input },
                { label: "Valuation", value: recommendation?.valuation_input },
              ].map((item) => (
                <div key={item.label} className="p-2.5 bg-[#0a0d14] rounded-lg text-center">
                  <div className="text-[10px] text-slate-500 uppercase">{item.label}</div>
                  <div className="text-sm font-bold text-slate-200 mt-0.5">{item.value ?? "N/A"}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Catalyst Timeline Tab ── */}
      {activeTab === "timeline" && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-[#1e293b] pb-4">
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center space-x-2">
                <Calendar className="w-4 h-4 text-sky-400" />
                <span>Catalyst Timeline</span>
              </h3>
              <p className="text-xs text-slate-400 mt-1">Historical catalysts and their market impact</p>
            </div>
            <span className="text-[11px] text-slate-500">{timeline.length} events</span>
          </div>

          {timeline.length === 0 ? (
            <div className="text-center py-8">
              <Calendar className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-500">No catalyst events recorded for this stock yet.</p>
              <p className="text-[11px] text-slate-600 mt-1">Events appear as the system detects market-moving news.</p>
            </div>
          ) : (
            <div className="relative">
              <div className="absolute left-4 top-0 bottom-0 w-px bg-[#1e293b]" />
              <div className="space-y-1">
                {timeline.map((item: any, idx: number) => {
                  const isExpanded = expandedTimeline === idx;
                  const impactStyle = IMPACT_STYLES[item.impact] || IMPACT_STYLES.LOW;
                  const sentimentStyle = SENTIMENT_STYLES[item.sentiment] || SENTIMENT_STYLES.neutral;

                  return (
                    <div key={idx} className="relative pl-10">
                      <div className={`absolute left-2.5 top-4 w-3 h-3 rounded-full border-2 ${
                        item.impact === "CRITICAL" ? "bg-rose-500 border-rose-400" :
                        item.impact === "HIGH" ? "bg-amber-500 border-amber-400" :
                        item.impact === "MEDIUM" ? "bg-sky-500 border-sky-400" :
                        "bg-slate-600 border-slate-500"
                      }`} />

                      <button
                        onClick={() => setExpandedTimeline(isExpanded ? null : idx)}
                        className="w-full text-left p-3 rounded-lg hover:bg-[#0a0d14] transition-colors"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1 flex-1 min-w-0">
                            <div className="flex items-center flex-wrap gap-2">
                              <span className="text-[11px] text-slate-500 font-mono">
                                {item.date ? relativeTime(item.date) : "Recent"}
                              </span>
                              <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase rounded border ${impactStyle}`}>
                                {item.impact}
                              </span>
                              <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase rounded border ${sentimentStyle}`}>
                                {item.sentiment}
                              </span>
                              {item.event && (
                                <span className="text-[10px] text-slate-400 font-semibold">
                                  {item.event}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-200 line-clamp-2">{item.headline}</p>

                            <div className="flex items-center gap-3 text-[11px]">
                              {item.price_reaction !== null && item.price_reaction !== undefined && (
                                <span className={`font-bold ${item.price_reaction >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                                  {item.price_reaction >= 0 ? "+" : ""}{item.price_reaction.toFixed(2)}%
                                </span>
                              )}
                              {item.volume_ratio !== null && item.volume_ratio !== undefined && (
                                <span className="text-slate-400">
                                  {item.volume_ratio.toFixed(1)}× avg volume
                                </span>
                              )}
                              {item.source && (
                                <span className="text-slate-500">{item.source}</span>
                              )}
                            </div>
                          </div>

                          {item.long_term_view || item.short_term_view ? (
                            <span className="text-slate-600 text-xs mt-1">{isExpanded ? "−" : "+"}</span>
                          ) : null}
                        </div>
                      </button>

                      {isExpanded && (item.long_term_view || item.short_term_view) && (
                        <div className="ml-3 mb-3 p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b] space-y-3">
                          {item.short_term_view && (
                            <div>
                              <h5 className="text-[10px] text-sky-400 uppercase font-bold mb-1 flex items-center space-x-1">
                                <Clock className="w-2.5 h-2.5" />
                                <span>Short-Term View</span>
                              </h5>
                              <p className="text-[11px] text-slate-300 leading-relaxed">{item.short_term_view}</p>
                            </div>
                          )}
                          {item.long_term_view && (
                            <div>
                              <h5 className="text-[10px] text-emerald-400 uppercase font-bold mb-1 flex items-center space-x-1">
                                <TrendingUp className="w-2.5 h-2.5" />
                                <span>Long-Term View</span>
                              </h5>
                              <p className="text-[11px] text-slate-300 leading-relaxed">{item.long_term_view}</p>
                            </div>
                          )}
                          {item.url && (
                            <a href={item.url} target="_blank" rel="noopener noreferrer"
                              className="inline-flex items-center space-x-1 text-[10px] text-sky-400 hover:text-sky-300 font-semibold">
                              <ExternalLink className="w-2.5 h-2.5" />
                              <span>Read full article</span>
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── News & Catalysts Tab ── */}
      {activeTab === "news" && (
        <div className="space-y-6">
          {catalysts?.catalysts?.length > 0 && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-3">
              <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2">
                <Calendar className="w-4 h-4 text-sky-400" />
                <span>Detected Catalysts & Events</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {catalysts.catalysts.map((cat: any, idx: number) => (
                  <div key={idx} className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b] text-xs space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-slate-200">{cat.title}</span>
                      <span className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase border flex-shrink-0 ${
                        cat.impact === "high" ? "bg-rose-500/10 text-rose-400 border-rose-500/20" : "bg-sky-500/10 text-sky-400 border-sky-500/20"
                      }`}>{cat.impact} Impact</span>
                    </div>
                    {cat.description && <p className="text-slate-400 text-[11px]">{cat.description}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2">
              <Newspaper className="w-4 h-4 text-sky-400" />
              <span>News & Sentiment ({sentiment?.overall_sentiment || "Neutral"})</span>
            </h3>

            {news && news.length > 0 ? (
              <div className="space-y-3">
                {news.map((item: any, idx: number) => (
                  <div key={idx} className="p-3.5 bg-[#0a0d14] rounded-lg border border-[#1e293b] space-y-1">
                    <div className="flex items-start justify-between gap-3">
                      <a href={item.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-xs text-slate-200 hover:text-sky-400 flex items-center space-x-1">
                        <span>{item.title}</span>
                        <ExternalLink className="w-3 h-3 text-slate-500 flex-shrink-0" />
                      </a>
                      <span className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase flex-shrink-0 border ${
                        item.sentiment_label === "positive" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
                        item.sentiment_label === "negative" ? "bg-rose-500/10 text-rose-400 border-rose-500/20" :
                        "bg-slate-800 text-slate-400 border-slate-700"
                      }`}>{item.sentiment_label || "Neutral"}</span>
                    </div>
                    {item.summary && <p className="text-[11px] text-slate-400 line-clamp-2">{item.summary}</p>}
                    {item.published_at && (() => {
                      const d = new Date(item.published_at);
                      return isNaN(d.getTime()) ? null : (
                        <p className="text-[10px] text-slate-500">
                          {relativeTime(item.published_at)}
                          <span className="ml-1 opacity-60">({d.toLocaleDateString()})</span>
                        </p>
                      );
                    })()}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 py-4 text-center">No recent news available for this ticker.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
