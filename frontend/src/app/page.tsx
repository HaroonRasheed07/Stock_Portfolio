"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import {
  TrendingUp, TrendingDown, AlertTriangle, ShieldCheck,
  PieChart, RefreshCw, Upload, Sparkles, ArrowUpRight
} from "lucide-react";
import {
  PieChart as RePieChart, Pie, Cell, ResponsiveContainer, Tooltip
} from "recharts";

const COLORS = ["#0284c7", "#0d9488", "#16a34a", "#ca8a04", "#dc2626", "#9333ea", "#2563eb", "#475569"];

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [performance, setPerformance] = useState<any>(null);
  const [riskData, setRiskData] = useState<any>(null);
  const [catalystSummary, setCatalystSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [catalystError, setCatalystError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      setRiskError(null);
      setCatalystError(null);

      // Fire all 4 requests in parallel, update state as each resolves
      const portfolioPromise = fetchAPI<any>("/portfolio");
      const perfPromise = fetchAPI<any>("/portfolio/performance");
      const riskPromise = fetchAPI<any>("/portfolio/risk-summary");
      const catalystPromise = fetchAPI<any>("/catalysts/summary");

      // Fast endpoints update immediately — use allSettled so one failure doesn't block others
      Promise.allSettled([portfolioPromise, perfPromise, riskPromise, catalystPromise]).then(
        ([portfolioRes, perfRes, riskRes, catalystRes]) => {
          if (!mountedRef.current) return;
          if (portfolioRes.status === "fulfilled") setSummary(portfolioRes.value);
          if (perfRes.status === "fulfilled") setPerformance(perfRes.value);
          if (riskRes.status === "fulfilled") setRiskData(riskRes.value);
          else if (riskRes.status === "rejected") setRiskError("Unable to load risk data. Market data may be unavailable.");
          if (catalystRes.status === "fulfilled") setCatalystSummary(catalystRes.value);
          else if (catalystRes.status === "rejected") setCatalystError("Unable to load catalyst data. News feed may be unavailable.");
        }
      );

      // Wait for the critical one (portfolio summary) to determine loading state
      await portfolioPromise;
    } catch (err: any) {
      if (mountedRef.current) setError(err.message || "Failed to connect to backend engine.");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  };

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      await fetchAPI("/portfolio/refresh", { method: "POST" });
      await loadData();
    } catch (err: any) {
      alert("Refresh error: " + err.message);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    // Fire warmup in background — do NOT block dashboard on it
    fetchAPI<any>("/stocks/warmup").catch(() => {});
    // Load dashboard data immediately
    loadData();
  }, []);

  const sectorData = performance?.sector_allocation
    ? Object.entries(performance.sector_allocation).map(([name, value]) => ({ name, value }))
    : [];

  if (error && !summary) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6 text-center space-y-4">
        <AlertTriangle className="w-12 h-12 text-red-400 mx-auto" />
        <h2 className="text-lg font-bold text-red-200">Engine Connection Issue</h2>
        <p className="text-sm text-slate-400">{error}</p>
        <button
          onClick={loadData}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg border border-slate-700 text-slate-200"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Top Header / Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Portfolio Dashboard</h1>
          <p className="text-xs text-slate-400 mt-1">Long-Term Investment Intelligence Overview</p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center space-x-2 px-3 py-2 bg-[#121824] hover:bg-slate-800 border border-[#1e293b] rounded-lg text-xs text-slate-300 font-medium transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
            <span>{refreshing ? "Refreshing Prices..." : "Refresh Live Prices"}</span>
          </button>
          <Link
            href="/portfolio"
            className="flex items-center space-x-2 px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-medium transition-colors"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Upload Portfolio CSV</span>
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5">
          <p className="text-xs text-slate-400 font-medium">Total Portfolio Value</p>
          <p className="text-2xl font-bold text-slate-100 mt-2">{formatCurrency(summary?.total_value)}</p>
          <div className="flex items-center space-x-2 mt-2 text-xs">
            <span className={summary?.day_change >= 0 ? "text-emerald-400" : "text-rose-400"}>
              {formatPercent(summary?.day_change_pct)} (Today)
            </span>
          </div>
        </div>

        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5">
          <p className="text-xs text-slate-400 font-medium">Total Unrealized Return</p>
          <p className={`text-2xl font-bold mt-2 ${summary?.total_gain_loss >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {formatCurrency(summary?.total_gain_loss)}
          </p>
          <p className="text-xs text-slate-400 mt-2">
            Cost Basis: {formatCurrency(summary?.total_cost_basis)}
          </p>
        </div>

        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5">
          <p className="text-xs text-slate-400 font-medium">Holdings & Allocation</p>
          <p className="text-2xl font-bold text-slate-100 mt-2">{summary?.num_holdings || 0} Positions</p>
          <p className="text-xs text-slate-400 mt-2">Established US Stocks & ETFs</p>
        </div>

        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5">
          <p className="text-xs text-slate-400 font-medium">Risk & Health Status</p>
          <div className="flex items-center space-x-2 mt-2">
            {riskError ? (
              <>
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <span className="text-lg font-bold text-amber-300">Unavailable</span>
              </>
            ) : riskData?.risk_level === "High" || riskData?.risk_level === "Elevated" ? (
              <AlertTriangle className="w-5 h-5 text-amber-400" />
            ) : (
              <ShieldCheck className="w-5 h-5 text-sky-400" />
            )}
            <span className="text-lg font-bold text-slate-100">
              {riskError ? "" : riskData?.risk_level || "Loading..."}
            </span>
          </div>
          {riskError ? (
            <p className="text-xs text-amber-400 mt-2">{riskError}</p>
          ) : riskData?.warnings && riskData.warnings.length > 0 ? (
            <div className="mt-2 space-y-1">
              {riskData.warnings.map((w: string, i: number) => (
                <p key={i} className="text-xs text-amber-400">{w}</p>
              ))}
            </div>
          ) : (
            <p className="text-xs text-emerald-400 mt-2">No issues detected</p>
          )}
        </div>
      </div>

      {/* Sector Allocation & Performers */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Sector Allocation Donut Chart */}
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 lg:col-span-1 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2">
              <PieChart className="w-4 h-4 text-sky-400" />
              <span>Sector Breakdown</span>
            </h3>
            <p className="text-xs text-slate-400 mt-1">Portfolio allocation across sectors</p>
          </div>

          <div className="h-64 my-4">
            {sectorData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RePieChart>
                  <Pie
                    data={sectorData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {sectorData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(val: any) => [`${Number(val || 0).toFixed(1)}%`, "Allocation"]}
                    contentStyle={{ backgroundColor: "#0a0d14", borderColor: "#1e293b", borderRadius: "8px", color: "#f8fafc" }}
                  />
                </RePieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-slate-500">
                No sector data available
              </div>
            )}
          </div>

          <div className="space-y-1 text-xs max-h-32 overflow-y-auto pr-1">
            {sectorData.map((item: any, idx: number) => (
              <div key={item.name} className="flex items-center justify-between text-slate-400">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }}></span>
                  <span className="truncate max-w-[140px]">{String(item.name)}</span>
                </div>
                <span className="font-semibold text-slate-300">{String(item.value)}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Top & Worst Performers */}
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 lg:col-span-2 space-y-6">
          <div>
            <h3 className="text-sm font-bold text-slate-200">Top Gainers in Portfolio</h3>
            <div className="mt-3 space-y-2">
              {performance?.top_performers?.slice(0, 3).map((item: any) => (
                <div key={item.symbol} className="flex items-center justify-between p-3 rounded-lg bg-[#0a0d14] border border-[#1e293b]">
                  <div>
                    <Link href={`/stocks/${item.symbol}`} className="font-bold text-sm text-slate-200 hover:text-sky-400 flex items-center space-x-1">
                      <span>{item.symbol}</span>
                      <ArrowUpRight className="w-3 h-3" />
                    </Link>
                    <p className="text-xs text-slate-400 truncate max-w-[200px]">{item.name}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-sm text-slate-200">{formatCurrency(item.current_value)}</p>
                    <p className="text-xs text-emerald-400 font-medium">{formatPercent(item.unrealized_gain_pct)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-bold text-slate-200">Underperforming Positions</h3>
            <div className="mt-3 space-y-2">
              {performance?.worst_performers?.slice(0, 3).map((item: any) => (
                <div key={item.symbol} className="flex items-center justify-between p-3 rounded-lg bg-[#0a0d14] border border-[#1e293b]">
                  <div>
                    <Link href={`/stocks/${item.symbol}`} className="font-bold text-sm text-slate-200 hover:text-sky-400 flex items-center space-x-1">
                      <span>{item.symbol}</span>
                      <ArrowUpRight className="w-3 h-3" />
                    </Link>
                    <p className="text-xs text-slate-400 truncate max-w-[200px]">{item.name}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-sm text-slate-200">{formatCurrency(item.current_value)}</p>
                    <p className={`text-xs font-medium ${item.unrealized_gain_pct < 0 ? "text-rose-400" : "text-emerald-400"}`}>
                      {formatPercent(item.unrealized_gain_pct)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Catalyst Summary */}
      {catalystError && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-5 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-amber-300">Catalyst data unavailable</p>
            <p className="text-[11px] text-slate-400 mt-1">{catalystError}</p>
          </div>
        </div>
      )}
      {catalystSummary && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <span>Portfolio Catalyst Summary</span>
            </h3>
            <Link href="/catalyst-watch" className="text-xs text-sky-400 hover:text-sky-300 font-medium">
              View All →
            </Link>
          </div>
          <p className="text-[11px] text-slate-400 mb-4">
            News events from the last 7 days that directly affect companies you hold. A catalyst is any event (earnings, analyst actions, legal news, product launches) that could move a stock's price.
          </p>

          {/* Plain-language impact line */}
          <div className="bg-[#0a0d14] border border-[#1e293b] rounded-lg p-3 mb-4">
            <p className="text-xs text-slate-300">
              <span className="font-semibold text-slate-200">What this means: </span>
              {catalystSummary.portfolio_impact_summary || "No significant news detected for your holdings this week."}
            </p>
            {catalystSummary.top_event && (
              <p className="text-xs text-slate-400 mt-1.5">
                <span className="font-semibold text-slate-300">Highest impact: </span>
                <span className="text-sky-400 font-semibold">{catalystSummary.top_event.symbol}</span>
                {" — "}
                {catalystSummary.top_event.headline?.slice(0, 120)}
                {catalystSummary.top_event.headline?.length > 120 ? "…" : ""}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-[#0a0d14] border border-[#1e293b] rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-slate-100">{catalystSummary.portfolio_catalysts_7d ?? 0}</p>
              <p className="text-xs text-slate-400 mt-1">Catalysts Affecting Your Holdings (7d)</p>
            </div>
            <div className="bg-[#0a0d14] border border-[#1e293b] rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-emerald-400">{catalystSummary.portfolio_sentiment?.positive ?? 0}</p>
              <p className="text-xs text-slate-400 mt-1">Positive</p>
            </div>
            <div className="bg-[#0a0d14] border border-[#1e293b] rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-rose-400">{catalystSummary.portfolio_sentiment?.negative ?? 0}</p>
              <p className="text-xs text-slate-400 mt-1">Negative</p>
            </div>
            <div className="bg-[#0a0d14] border border-[#1e293b] rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-sky-400">{catalystSummary.unread_alerts ?? 0}</p>
              <p className="text-xs text-slate-400 mt-1">Unread Alerts</p>
            </div>
          </div>

          {catalystSummary.recent_events && catalystSummary.recent_events.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">Latest portfolio-relevant events</p>
              {catalystSummary.recent_events.slice(0, 3).map((evt: any, idx: number) => (
                <div key={idx} className="flex items-center justify-between gap-3 p-3 rounded-lg bg-[#0a0d14] border border-[#1e293b]">
                  <div className="flex items-center space-x-3 min-w-0">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      evt.impact_level === "CRITICAL" ? "bg-rose-500" :
                      evt.impact_level === "HIGH" ? "bg-amber-500" :
                      evt.impact_level === "MEDIUM" ? "bg-sky-500" : "bg-slate-500"
                    }`}></span>
                    <div className="min-w-0">
                      <p className="text-sm text-slate-200 font-medium truncate">{evt.title || evt.headline}</p>
                      <p className="text-xs text-slate-400">{evt.symbol} · {evt.catalyst_type?.replace(/_/g, " ")}</p>
                    </div>
                  </div>
                  <span className={`flex-shrink-0 text-xs font-semibold px-2 py-1 rounded ${
                    evt.impact_level === "CRITICAL" ? "bg-rose-500/10 text-rose-400" :
                    evt.impact_level === "HIGH" ? "bg-amber-500/10 text-amber-400" :
                    "bg-sky-500/10 text-sky-400"
                  }`}>{evt.impact_level}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
