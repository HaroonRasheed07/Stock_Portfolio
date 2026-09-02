"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import { RefreshCw, AlertTriangle, ArrowUpCircle, ArrowDownCircle, Target, ArrowRight, ShieldCheck, TrendingDown, TrendingUp, Clock, AlertOctagon, CheckCircle } from "lucide-react";

const confidenceColor = (c: string) => {
  const map: Record<string, string> = {
    "High": "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    "Medium-High": "text-sky-400 bg-sky-500/10 border-sky-500/20",
    "Medium": "text-amber-400 bg-amber-500/10 border-amber-500/20",
    "Low": "text-slate-400 bg-slate-500/10 border-slate-500/20",
  };
  return map[c] || map["Low"];
};

const actionColor = (a: string) => {
  const map: Record<string, string> = {
    "SELL": "text-rose-400",
    "REDUCE": "text-amber-400",
    "SWAP_CANDIDATE": "text-sky-400",
    "MONITOR": "text-slate-400",
    "HOLD": "text-emerald-400",
  };
  return map[a] || "text-slate-400";
};

export default function RebalancingPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAPI<any>("/portfolio/rebalancing");
      setData(result);
    } catch (err: any) {
      setError("Could not load rebalancing analysis. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="space-y-8 max-w-4xl mx-auto px-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Portfolio Rebalancing</h1>
          <p className="text-xs text-slate-400 mt-1">Stock-to-stock swap recommendations with portfolio impact analysis</p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center space-x-2 px-3 py-2 bg-[#121824] hover:bg-slate-800 border border-[#1e293b] rounded-lg text-xs text-slate-300 font-medium"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {loading ? (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center space-y-4">
          <div className="animate-pulse space-y-3">
            <div className="h-4 w-48 bg-slate-800 rounded mx-auto"></div>
            <div className="h-3 w-64 bg-slate-800 rounded mx-auto"></div>
          </div>
          <p className="text-xs text-slate-400 animate-pulse">Analysing portfolio allocation...</p>
        </div>
      ) : error ? (
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-6 text-center space-y-4">
          <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
          <h3 className="text-sm font-bold text-rose-200">Unable to Load</h3>
          <p className="text-xs text-slate-400">{error}</p>
        </div>
      ) : !data ? (
        <div className="p-6 text-center text-xs text-slate-500">No data available.</div>
      ) : (
        <div className="space-y-6">
          {/* Score + Summary */}
          <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 flex items-center justify-between flex-wrap gap-3">
            <div>
              <span className="text-xs text-slate-400 font-medium">Rebalancing Score</span>
              <p className="text-3xl font-extrabold text-slate-100 mt-1">{data.rebalancing_score}/100</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-400">Total Value</p>
              <p className="text-sm font-bold text-slate-200">${data.total_portfolio_value?.toLocaleString()}</p>
              <p className="text-xs text-slate-400 mt-1">{data.total_positions} positions</p>
            </div>
          </div>

          {data.summary && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5">
              <p className="text-xs text-slate-300 leading-relaxed">{data.summary}</p>
            </div>
          )}

          {/* ACTIONABLE PLAN: Step-by-step priority actions */}
          {data.suggestions && data.suggestions.length > 0 && (
            <div className="bg-gradient-to-br from-sky-500/5 to-emerald-500/5 border border-sky-500/20 rounded-xl p-5 space-y-3">
              <h3 className="text-sm font-bold text-sky-300 flex items-center gap-2">
                <CheckCircle className="w-4 h-4" /> Action Plan
              </h3>
              <p className="text-[11px] text-slate-400">Prioritized actions based on portfolio impact. Start with highest priority.</p>
              <div className="space-y-2">
                {data.suggestions.slice(0, 5).map((s: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 text-[11px]">
                    <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                      s.priority === "high"
                        ? "bg-rose-500/20 text-rose-400"
                        : s.priority === "medium"
                        ? "bg-amber-500/20 text-amber-400"
                        : "bg-slate-500/20 text-slate-400"
                    }`}>
                      {i + 1}
                    </span>
                    <div>
                      <p className="text-slate-200 font-semibold">
                        {s.action.replace(/_/g, " ").toUpperCase()}
                        {s.symbol && ` — ${s.symbol}`}
                        {s.sector && ` (${s.sector})`}
                      </p>
                      <p className="text-slate-400 mt-0.5">{s.reason}</p>
                      {s.replacement && (
                        <p className="text-emerald-400 mt-0.5">
                          Replace with {s.replacement.replacement_ticker} ({s.replacement.replacement_name})
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Stock-Level Swap Recommendations */}
          {data.stock_swaps && data.stock_swaps.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-sky-400 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4" /> Stock-Level Recommendations
              </h3>
              <p className="text-[11px] text-slate-500">
                Each recommendation requires multiple meaningful signals. Single weak indicators do not trigger action.
              </p>

              {data.stock_swaps.map((swap: any, i: number) => (
                <div
                  key={i}
                  className={`bg-[#121824] border rounded-xl p-5 space-y-4 ${
                    swap.action === "SELL"
                      ? "border-rose-500/20"
                      : swap.action === "REDUCE"
                      ? "border-amber-500/20"
                      : "border-[#1e293b]"
                  }`}
                >
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="text-center">
                        <p className="text-lg font-extrabold text-slate-100">{swap.symbol}</p>
                        <p className="text-[10px] text-slate-500">{swap.name}</p>
                      </div>
                      {swap.replacement && (
                        <>
                          <ArrowRight className="w-4 h-4 text-sky-400" />
                          <div className="text-center">
                            <p className="text-lg font-extrabold text-sky-400">{swap.replacement.replacement_ticker}</p>
                            <p className="text-[10px] text-slate-500">{swap.replacement.replacement_name}</p>
                          </div>
                        </>
                      )}
                    </div>
                    <div className="text-right">
                      <span className={`text-xs font-bold ${actionColor(swap.action)}`}>{swap.action}</span>
                      <span className={`ml-2 px-1.5 py-0.5 text-[10px] font-bold rounded border ${confidenceColor(swap.confidence)}`}>
                        {swap.confidence}
                      </span>
                    </div>
                  </div>

                  {/* Current Position */}
                  <div className="grid grid-cols-3 gap-3 text-[11px]">
                    <div className="bg-slate-800/40 rounded-lg p-2.5">
                      <p className="text-slate-500">Current Value</p>
                      <p className="text-slate-200 font-bold">${swap.current_value?.toLocaleString()}</p>
                    </div>
                    <div className="bg-slate-800/40 rounded-lg p-2.5">
                      <p className="text-slate-500">Portfolio Weight</p>
                      <p className="text-slate-200 font-bold">{swap.current_allocation_pct}%</p>
                    </div>
                    <div className="bg-slate-800/40 rounded-lg p-2.5">
                      <p className="text-slate-500">Unrealized P/L</p>
                      <p className={`font-bold ${swap.unrealized_gain_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                        {swap.unrealized_gain_pct >= 0 ? "+" : ""}{swap.unrealized_gain_pct}%
                      </p>
                    </div>
                  </div>

                  {/* Flags */}
                  {swap.flags && swap.flags.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wide font-semibold">Signals Detected</p>
                      <div className="flex flex-wrap gap-1.5">
                        {swap.flags.map((flag: any, fi: number) => (
                          <span
                            key={fi}
                            className={`px-2 py-0.5 text-[10px] rounded border ${
                              flag.severity === "high"
                                ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                                : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                            }`}
                          >
                            {flag.detail}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Explanation */}
                  {swap.explanation && (
                    <div className="space-y-2">
                      <div className="p-2.5 bg-slate-800/30 rounded-lg">
                        <p className="text-[10px] text-slate-500 uppercase tracking-wide font-semibold mb-1">Why This Action</p>
                        <p className="text-[11px] text-slate-300">{swap.explanation.why_action}</p>
                      </div>
                      <div className="p-2.5 bg-emerald-500/5 rounded-lg border border-emerald-500/10">
                        <p className="text-[10px] text-emerald-500 uppercase tracking-wide font-semibold mb-1">Why This Replacement</p>
                        <p className="text-[11px] text-slate-300">{swap.explanation.why_replacement}</p>
                      </div>
                      {swap.explanation.portfolio_benefit && (
                        <div className="p-2.5 bg-sky-500/5 rounded-lg border border-sky-500/10">
                          <p className="text-[10px] text-sky-500 uppercase tracking-wide font-semibold mb-1">Portfolio Benefit</p>
                          <p className="text-[11px] text-slate-300">{swap.explanation.portfolio_benefit}</p>
                        </div>
                      )}
                      {/* WHY NOT HOLD: Explain why continuing to hold is suboptimal */}
                      {swap.action !== "HOLD" && swap.action !== "MONITOR" && (
                        <div className="p-2.5 bg-amber-500/5 rounded-lg border border-amber-500/10">
                          <p className="text-[10px] text-amber-400 uppercase tracking-wide font-semibold mb-1 flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Why Not Just Hold?
                          </p>
                          <p className="text-[11px] text-slate-300">
                            {swap.flags?.some((f: any) => f.type === "severe_underperformance")
                              ? `Holding ${swap.symbol} means remaining exposed to ${Math.abs(swap.unrealized_gain_pct)}% unrealized loss with deteriorating fundamentals. The opportunity cost of waiting for recovery exceeds the benefit of switching to a higher-quality position.`
                              : swap.flags?.some((f: any) => f.type === "overconcentration")
                              ? `Continuing to hold ${swap.symbol} at ${swap.current_allocation_pct}% creates outsized single-stock risk. A market downturn in this position would disproportionately impact your portfolio.`
                              : swap.flags?.some((f: any) => f.type === "sector_overweight")
                              ? `Staying in ${swap.symbol} maintains overweight sector exposure. Reallocating to a different sector reduces correlation risk while maintaining quality.`
                              : `The combination of signals suggests this position is underperforming alternatives. Holding indefinitely means forgoing the improvement in risk-adjusted returns the replacement offers.`}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* PANIC-SELL PREVENTION: Show for SELL/REDUCE actions */}
                  {(swap.action === "SELL" || swap.action === "REDUCE") && (
                    <div className="p-3 bg-rose-500/5 rounded-lg border border-rose-500/10 flex items-start gap-3">
                      <AlertOctagon className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-[11px] font-bold text-rose-300">Important: This is not a panic-sell trigger</p>
                        <p className="text-[10px] text-slate-400 mt-1">
                          This recommendation is based on multiple quantitative signals (allocation, sector weight, peer comparison).
                          It is not a reaction to short-term price movement. Review the signals above and consider your personal
                          risk tolerance, tax implications, and investment timeline before acting. Consult a financial advisor for
                          large position changes.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* No Replacement */}
                  {swap.no_replacement_reason && (
                    <div className="p-2.5 bg-slate-800/30 rounded-lg">
                      <p className="text-[11px] text-slate-400 italic">{swap.no_replacement_reason}</p>
                    </div>
                  )}

                  {/* Replacement Detail */}
                  {swap.replacement && (
                    <div className="p-3 bg-emerald-500/5 rounded-lg border border-emerald-500/10">
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-[11px] font-bold text-emerald-400">Replacement Detail</p>
                        {swap.replacement.replacement_score && (
                          <span className="px-1.5 py-0.5 text-[10px] font-bold bg-emerald-500/10 text-emerald-400 rounded">
                            Score: {swap.replacement.replacement_score}/100
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className={`px-1.5 py-0.5 text-[9px] rounded ${
                          swap.replacement.same_sector
                            ? "bg-sky-500/10 text-sky-400"
                            : "bg-amber-500/10 text-amber-400"
                        }`}>
                          {swap.replacement.same_sector ? "Same Sector" : "Cross-Sector"}
                        </span>
                        <span className="text-[10px] text-slate-400">{swap.replacement.sector}</span>
                      </div>
                      {swap.replacement.why_this_replacement && (
                        <p className="text-[10px] text-slate-300">{swap.replacement.why_this_replacement}</p>
                      )}
                    </div>
                  )}

                  {/* Portfolio Impact */}
                  {swap.portfolio_impact && (
                    <div className="flex items-center gap-4 text-[10px] text-slate-500 pt-2 border-t border-[#1e293b]">
                      <span>Sector: {swap.portfolio_impact.current_sector_pct}%</span>
                      {swap.portfolio_impact.sector_would_change_to !== swap.portfolio_impact.current_sector_pct && (
                        <span>→ {swap.portfolio_impact.sector_would_change_to}%</span>
                      )}
                      {swap.portfolio_impact.risk_reduction && (
                        <span className="text-slate-400">Risk: {swap.portfolio_impact.risk_reduction}</span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Trade Suggestions (non-swap) */}
          {data.suggestions && data.suggestions.filter((s: any) => !s.action.startsWith("swap_")).length > 0 && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-3">
              <h3 className="text-sm font-bold text-sky-400 flex items-center gap-2">
                <Target className="w-4 h-4" /> Additional Suggestions
              </h3>
              <div className="space-y-2">
                {data.suggestions.filter((s: any) => !s.action.startsWith("swap_")).map((s: any, i: number) => (
                  <div
                    key={i}
                    className={`flex items-start gap-3 p-3 rounded-lg border ${
                      s.priority === "high"
                        ? "bg-rose-500/5 border-rose-500/10"
                        : s.priority === "medium"
                        ? "bg-amber-500/5 border-amber-500/10"
                        : "bg-slate-500/5 border-slate-500/10"
                    }`}
                  >
                    {s.action === "reduce" || s.action === "reduce_sector_exposure" ? (
                      <ArrowDownCircle className="w-3.5 h-3.5 text-rose-400 mt-0.5 shrink-0" />
                    ) : (
                      <ArrowUpCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                    )}
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-xs font-semibold text-slate-200">{s.action.replace(/_/g, " ").toUpperCase()}</p>
                        {s.symbol && (
                          <span className="px-1.5 py-0.5 bg-sky-500/10 text-sky-400 text-[10px] font-bold rounded border border-sky-500/20">
                            {s.symbol}
                          </span>
                        )}
                        {s.sector && (
                          <span className="px-1.5 py-0.5 bg-amber-500/10 text-amber-400 text-[10px] font-bold rounded border border-amber-500/20">
                            {s.sector}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">{s.reason}</p>
                      {s.estimated_impact && (
                        <p className="text-[11px] text-emerald-400 mt-0.5">Impact: {s.estimated_impact}</p>
                      )}
                      {s.replacement && (
                        <div className="mt-2 p-2 bg-emerald-500/5 rounded-lg border border-emerald-500/10">
                          <p className="text-[11px] font-bold text-emerald-400 mb-1">Potential Replacement</p>
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] text-rose-400 font-semibold">{s.symbol}</span>
                            <span className="text-[11px] text-slate-500">{'\u2192'}</span>
                            <span className="text-[11px] text-emerald-400 font-semibold">{s.replacement.replacement_ticker}</span>
                            <span className="text-[10px] text-slate-400">({s.replacement.replacement_name})</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Over Allocations */}
          {data.over_allocations && data.over_allocations.length > 0 && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-3">
              <h3 className="text-xs font-bold text-rose-400 uppercase tracking-wide">Overweight Positions</h3>
              {data.over_allocations.map((o: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-3 bg-rose-500/5 rounded-lg border border-rose-500/10">
                  <div>
                    <p className="text-xs font-bold text-slate-200">{o.symbol}</p>
                    <p className="text-[11px] text-slate-400">Current: {o.current_pct}%</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-bold text-rose-400">-{o.excess_pct}%</p>
                    <p className="text-[11px] text-slate-400">${o.estimated_amount?.toLocaleString()}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Sector Allocation */}
          {data.sector_allocation && data.sector_allocation.length > 0 && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-3">
              <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wide">Sector Allocation</h3>
              <div className="space-y-2">
                {data.sector_allocation.map((s: any, i: number) => (
                  <div key={i} className="flex items-center gap-3">
                    <p className="text-xs text-slate-300 w-40 shrink-0">{s.sector}</p>
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-sky-500 rounded-full"
                        style={{ width: `${Math.min(s.current_pct, 100)}%` }}
                      />
                    </div>
                    <p className="text-xs text-slate-400 w-16 text-right">{s.current_pct}%</p>
                    {s.target_pct != null && (
                      <p className="text-[10px] text-slate-500 w-12 text-right">Target: {s.target_pct}%</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
