"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import {
  TrendingUp, ShieldCheck, ArrowRight, AlertTriangle, Zap, Clock,
  CheckCircle, WifiOff, RefreshCw, Activity, Target, TrendingDown,
  BarChart3, Briefcase, ChevronDown, ChevronUp, AlertOctagon, Eye,
  ArrowUpDown, Star, Info, X, TrendingDown as TrendingDownIcon,
  Search, Plus,
} from "lucide-react";

/* ── Helpers ──────────────────────────────────────────────────────── */

function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return "just now";
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function formatExact(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true,
  });
}

function isMarketOpen(): { open: boolean; label: string; sublabel: string } {
  const now = new Date();
  const et = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const day = et.getDay();
  const mins = et.getHours() * 60 + et.getMinutes();
  if (day === 0 || day === 6)
    return { open: false, label: "Closed", sublabel: "Weekend — using latest market close" };
  if (mins < 570)
    return { open: false, label: "Closed", sublabel: "Pre-market — using latest market close" };
  if (mins < 960) {
    const hh = et.getHours().toString().padStart(2, "0");
    const mm = et.getMinutes().toString().padStart(2, "0");
    return { open: true, label: "Open", sublabel: `Market open — data refreshed at ${hh}:${mm} ET` };
  }
  return { open: false, label: "Closed", sublabel: "After hours — using latest market close" };
}

function fmt$(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "N/A";
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "N/A";
  const s = v.toFixed(1);
  return v >= 0 ? `+${s}%` : `${s}%`;
}

/* ── Color Maps ───────────────────────────────────────────────────── */

const maturityBadge = (m: string) => {
  const map: Record<string, string> = {
    EARLY: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20",
    DEVELOPING: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20",
    CONFIRMED: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
    MATURE: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
    EXTENDED: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20",
  };
  return map[m] || map.DEVELOPING;
};

const freshnessBadge = (f: string) => {
  const map: Record<string, string> = {
    Fresh: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
    Aging: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
    Stale: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20",
    Invalidated: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20",
  };
  return map[f] || map.Aging;
};

const signalBadge = (s: string) => {
  const m: Record<string, string> = {
    BUY: "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    WATCH: "text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/20",
    HOLD: "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20",
    AVOID: "text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/20",
  };
  return m[s] || m.WATCH;
};

const entryBadge = (e: string) => {
  const map: Record<string, string> = {
    ACTIONABLE: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
    EXTENDED: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
    WAIT_FOR_PULLBACK: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
    ENTRY_MISSED: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20",
    INVALIDATED: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20",
  };
  return map[e] || map.EXTENDED;
};

const actionBadge = (a: string) => {
  const m: Record<string, string> = {
    ADD: "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    HOLD: "text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/20",
    WATCH: "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20",
    REDUCE: "text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/20",
    SELL: "text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/20",
  };
  return m[a] || m.WATCH;
};

/* ── Types ────────────────────────────────────────────────────────── */

type Tab = "swing" | "longterm" | "swaps";
type SwingFilter = "all" | "fresh" | "developing" | "watch" | "aging" | "invalidated";
type Universe = "portfolio" | "watchlist" | "portfolio_watchlist" | "selected";

const UNIVERSE_OPTIONS: { value: Universe; label: string }[] = [
  { value: "portfolio", label: "Portfolio" },
  { value: "watchlist", label: "Watchlist" },
  { value: "portfolio_watchlist", label: "Portfolio + Watchlist" },
  { value: "selected", label: "Selected Stocks" },
];

/* ── Page ─────────────────────────────────────────────────────────── */

export default function TradingPage() {
  const [tab, setTab] = useState<Tab>("swing");
  const [swingFilter, setSwingFilter] = useState<SwingFilter>("all");
  const [universe, setUniverse] = useState<Universe>("portfolio");
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [tickerInput, setTickerInput] = useState("");
  const [tickerSearchResults, setTickerSearchResults] = useState<any[]>([]);
  const [tickerSearching, setTickerSearching] = useState(false);
  const [swingOpps, setSwingOpps] = useState<any[]>([]);
  const [nearMisses, setNearMisses] = useState<any[]>([]);
  const [swapRecs, setSwapRecs] = useState<any[]>([]);
  const [longTermOpps, setLongTermOpps] = useState<any[]>([]);
  const [swingData, setSwingData] = useState<any>(null);
  const [longTermData, setLongTermData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [rescanning, setRescanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showScoreDetail, setShowScoreDetail] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const tickerSearchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Persist universe preference in localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("trading_universe");
      if (saved && UNIVERSE_OPTIONS.some(o => o.value === saved)) {
        setUniverse(saved as Universe);
      }
      const savedSelected = localStorage.getItem("trading_selected_symbols");
      if (savedSelected) {
        setSelectedSymbols(JSON.parse(savedSelected));
      }
    } catch {}
  }, []);

  useEffect(() => {
    try { localStorage.setItem("trading_universe", universe); } catch {}
  }, [universe]);

  useEffect(() => {
    try { localStorage.setItem("trading_selected_symbols", JSON.stringify(selectedSymbols)); } catch {}
  }, [selectedSymbols]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; abortRef.current?.abort(); };
  }, []);

  /* ── Data Loading ─────────────────────────────────────────────── */

  const loadSwing = useCallback(async (refresh = false) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const reqId = ++requestIdRef.current;

    if (refresh) setRescanning(true); else setLoading(true);
    setError(null);
    try {
      let url = `/analytics/trading-opportunities?universe=${universe}`;
      if (universe === "selected" && selectedSymbols.length > 0) {
        url += `&selected_symbols=${selectedSymbols.join(",")}`;
      }
      if (refresh) url += `${url.includes("?") ? "&" : "?"}refresh=true`;
      const result = await fetchAPI<any>(url);
      if (!mountedRef.current || controller.signal.aborted || reqId !== requestIdRef.current) return;
      const opps = result?.opportunities || (Array.isArray(result) ? result : []);
      setSwingOpps(opps);
      setNearMisses(result?.near_misses || []);
      setSwapRecs(result?.swap_recommendations || []);
      setSwingData(result);
    } catch (err: any) {
      if (!mountedRef.current || controller.signal.aborted) return;
      const msg = err?.message || "";
      if (msg.includes("429")) setError("Market data provider busy. Wait a moment and retry.");
      else if (msg.includes("timeout") || msg.includes("Timeout"))
        setError("Market data request timed out. Showing cached data where available.");
      else setError("Could not load trading opportunities. Showing cached data.");
    } finally {
      if (mountedRef.current && !controller.signal.aborted) { setLoading(false); setRescanning(false); }
    }
  }, [universe, selectedSymbols]);

  const loadLongTerm = useCallback(async () => {
    try {
      const result = await fetchAPI<any>("/analytics/long-term-opportunities");
      if (!mountedRef.current) return;
      setLongTermOpps(result?.opportunities || []);
      setLongTermData(result);
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => { loadSwing(); loadLongTerm(); }, []);

  // Re-fetch when universe changes (debounced)
  useEffect(() => {
    if (universe !== "selected" || selectedSymbols.length > 0) {
      const t = setTimeout(() => loadSwing(), 300);
      return () => clearTimeout(t);
    }
  }, [universe]);

  // Re-fetch when selected symbols change
  useEffect(() => {
    if (universe === "selected" && selectedSymbols.length > 0) {
      const t = setTimeout(() => loadSwing(), 500);
      return () => clearTimeout(t);
    }
  }, [selectedSymbols]);

  /* ── Ticker Search / Selected Stocks ────────────────────────── */

  const searchTicker = useCallback(async (q: string) => {
    if (!q || q.length < 1) { setTickerSearchResults([]); return; }
    setTickerSearching(true);
    try {
      const results = await fetchAPI<any[]>(`/stocks/search?q=${encodeURIComponent(q)}`);
      if (!mountedRef.current) return;
      setTickerSearchResults(results || []);
    } catch {
      setTickerSearchResults([]);
    } finally {
      if (mountedRef.current) setTickerSearching(false);
    }
  }, []);

  const handleTickerInput = useCallback((val: string) => {
    setTickerInput(val);
    if (tickerSearchTimeout.current) clearTimeout(tickerSearchTimeout.current);
    tickerSearchTimeout.current = setTimeout(() => searchTicker(val), 250);
  }, [searchTicker]);

  const addSymbol = useCallback((sym: string) => {
    const normalized = sym.toUpperCase().trim();
    if (!normalized || selectedSymbols.includes(normalized)) return;
    setSelectedSymbols(prev => [...prev, normalized]);
    setTickerInput("");
    setTickerSearchResults([]);
  }, [selectedSymbols]);

  const removeSymbol = useCallback((sym: string) => {
    setSelectedSymbols(prev => prev.filter(s => s !== sym));
  }, []);

  const handleTickerKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const val = tickerInput.toUpperCase().trim();
      if (val) addSymbol(val);
    }
  }, [tickerInput, addSymbol]);

  /* ── Derived State ────────────────────────────────────────────── */

  const market = isMarketOpen();
  const dq = swingData?.data_quality || {};
  const ds = swingData?.data_source || "live";
  const dataStatus = swingData?.data_status || "success";
  const isPartial = ds === "partial" || ds === "stale";
  const isUnavailable = dataStatus === "provider_unavailable";
  const totalAnalyzed = dq.holdings_with_data || 0;
  const totalEligible = dq.eligible_holdings || 0;
  const scanDuration = dq.scan_duration_seconds || 0;

  // Summary counts by maturity
  const freshCount = swingOpps.filter((o: any) => o.maturity === "CONFIRMED" || o.maturity === "MATURE").length;
  const developingCount = swingOpps.filter((o: any) => o.maturity === "DEVELOPING" || o.maturity === "EARLY").length;
  const watchCount = swingOpps.filter((o: any) => o.entry_status === "EXTENDED" || o.entry_status === "WAIT_FOR_PULLBACK").length;
  const invalidatedCount = swingOpps.filter((o: any) => o.entry_status === "INVALIDATED" || o.freshness === "Invalidated").length;

  // Filter swing opportunities by sub-tab
  const filteredOpps = swingOpps.filter((op: any) => {
    if (swingFilter === "all") return true;
    if (swingFilter === "fresh") return op.maturity === "CONFIRMED" || op.maturity === "MATURE";
    if (swingFilter === "developing") return op.maturity === "DEVELOPING" || op.maturity === "EARLY";
    if (swingFilter === "watch") return op.entry_status === "EXTENDED" || op.entry_status === "WAIT_FOR_PULLBACK";
    if (swingFilter === "aging") return op.freshness === "Aging" || op.freshness === "Stale";
    if (swingFilter === "invalidated") return op.entry_status === "INVALIDATED" || op.freshness === "Invalidated";
    return true;
  });

  const hasGoldenCross = (op: any) =>
    op.technical_factors?.some((f: string) => f?.includes("Golden Cross")) || false;

  const entryStatusText = (e: string) => {
    const m: Record<string, string> = {
      ACTIONABLE: "Confirmed",
      EXTENDED: "Extended",
      WAIT_FOR_PULLBACK: "Wait for Pullback",
      ENTRY_MISSED: "Entry Missed",
      INVALIDATED: "Invalidated",
    };
    return m[e] || e;
  };

  /* ── Render ───────────────────────────────────────────────────── */

  return (
    <div className="space-y-6 px-4 max-w-6xl mx-auto">

      {/* ═══ HEADER ═══════════════════════════════════════════════ */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            Trading Opportunities
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-2xl">
            Technical setups {universe === "portfolio" ? "across your portfolio" : universe === "watchlist" ? "from your watchlist" : universe === "portfolio_watchlist" ? "across portfolio and watchlist" : "for selected stocks"}, ranked by setup quality, trend confirmation, momentum, risk and freshness.
          </p>

          {/* ═══ SCAN UNIVERSE SELECTOR ══════════════════════════ */}
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            <div className="relative">
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1 block">Scan Universe</label>
              <div className="relative">
                <select
                  value={universe}
                  onChange={(e) => setUniverse(e.target.value as Universe)}
                  className="appearance-none bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-lg px-3 py-1.5 pr-8 text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer hover:border-sky-500/50 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                >
                  {UNIVERSE_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 pointer-events-none" />
              </div>
            </div>
            {swingData?.scanned_count != null && (
              <span className="text-[11px] text-slate-500 mt-4">
                <strong className="text-slate-700 dark:text-slate-300">{swingData.scanned_count}</strong> stocks scanned
              </span>
            )}
          </div>

          {/* ═══ SELECTED STOCKS INPUT ══════════════════════════ */}
          {universe === "selected" && (
            <div className="mt-3 p-3 bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl">
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2 block">Selected Stocks</label>
              <div className="relative mb-2">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  value={tickerInput}
                  onChange={(e) => handleTickerInput(e.target.value)}
                  onKeyDown={handleTickerKeyDown}
                  placeholder="Search ticker... (e.g. AAPL, NVDA)"
                  className="w-full pl-8 pr-3 py-1.5 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-[#1e293b] rounded-lg text-xs text-slate-700 dark:text-slate-300 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                />
                {tickerSearching && (
                  <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-slate-400">Searching...</span>
                )}
              </div>
              {/* Ticker search results dropdown */}
              {tickerSearchResults.length > 0 && (
                <div className="mb-2 max-h-40 overflow-y-auto border border-slate-200 dark:border-[#1e293b] rounded-lg">
                  {tickerSearchResults.slice(0, 6).map((r: any) => (
                    <button
                      key={r.symbol}
                      onClick={() => addSymbol(r.symbol)}
                      disabled={selectedSymbols.includes(r.symbol)}
                      className="w-full flex items-center justify-between px-3 py-1.5 text-xs hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors disabled:opacity-40 text-left"
                    >
                      <span className="font-bold text-slate-700 dark:text-slate-200">{r.symbol}</span>
                      <span className="text-slate-500 truncate ml-2">{r.name}</span>
                    </button>
                  ))}
                </div>
              )}
              {/* Selected ticker chips */}
              {selectedSymbols.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {selectedSymbols.map(sym => (
                    <span key={sym} className="flex items-center gap-1 px-2 py-1 bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20 rounded-lg text-[11px] font-semibold">
                      {sym}
                      <button onClick={() => removeSymbol(sym)} className="ml-0.5 hover:text-rose-500 transition-colors">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-[10px] text-slate-400">Enter ticker symbols to scan. Press Enter or click to add.</p>
              )}
            </div>
          )}
          <div className="flex items-center gap-3 mt-2 flex-wrap text-[11px]">
            <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded font-semibold border ${
              market.open
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                : "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20"
            }`}>
              <Activity className="w-3 h-3" />{market.label}
            </span>
            <span className="text-slate-500 dark:text-slate-500">{market.sublabel}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {swingOpps[0]?.last_updated && (
            <span className="text-[11px] text-slate-500 hidden sm:block">
              Last updated: {relativeTime(swingOpps[0].last_updated)}
            </span>
          )}
          <button
            onClick={() => loadSwing(true)}
            disabled={rescanning || loading}
            className="flex items-center space-x-2 px-3 py-2 bg-white dark:bg-[#121824] hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-200 dark:border-[#1e293b] rounded-lg text-xs text-slate-600 dark:text-slate-300 font-medium disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${rescanning ? "animate-spin" : ""}`} />
            <span>{rescanning ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* ═══ MARKET STATUS ═══════════════════════════════════════ */}
      <div className="bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Activity className={`w-4 h-4 ${market.open ? "text-emerald-500" : "text-slate-400"}`} />
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">Market Status</span>
            </div>
            <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${
              market.open
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                : "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20"
            }`}>
              {market.label}
            </span>
          </div>
          <div className="flex items-center gap-4 text-[11px] text-slate-500">
            {totalEligible > 0 && (
              <span>Data coverage: <strong className="text-slate-700 dark:text-slate-300">{totalAnalyzed}/{totalEligible} holdings</strong></span>
            )}
            {scanDuration > 0 && <span>Scan: {scanDuration}s</span>}
          </div>
        </div>
        {isPartial && totalAnalyzed > 0 && (
          <div className="mt-3 rounded-lg p-2.5 bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-700 dark:text-amber-300">
            Market data partially unavailable. Showing the most recent valid data where available.
          </div>
        )}
        {isUnavailable && !loading && (
          <div className="mt-3 rounded-lg p-2.5 bg-rose-500/10 border border-rose-500/20 text-[11px] text-rose-700 dark:text-rose-300">
            Market data temporarily unavailable. Showing the most recent valid data where available.
          </div>
        )}
      </div>

      {/* ═══ DEV MODE DIAGNOSTIC SUMMARY ═══════════════════════ */}
      {typeof process !== "undefined" && (process.env as any).NODE_ENV === "development" && !loading && swingData && (
        <details className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg text-[10px] font-mono text-slate-500 p-3">
          <summary className="cursor-pointer font-sans font-semibold text-[11px] text-slate-600 dark:text-slate-400">
            Trading Scan Diagnostics
          </summary>
          <div className="mt-2 space-y-1 grid grid-cols-2 sm:grid-cols-3 gap-x-4">
            <span>Holdings: <strong>{dq.total_holdings || 0}</strong></span>
            <span>Eligible: <strong>{dq.eligible_holdings || 0}</strong></span>
            <span>Live data: <strong>{dq.holdings_with_data || 0}</strong></span>
            <span>Failed: <strong>{(dq.failed_symbols || []).length}</strong></span>
            <span>Candidates: <strong>{dq.candidates_found || 0}</strong></span>
            <span>Opportunities: <strong>{dq.opportunities_found || 0}</strong></span>
            <span>Near misses: <strong>{dq.near_miss_count || 0}</strong></span>
            <span>Swaps: <strong>{dq.swap_count || 0}</strong></span>
            <span>Duration: <strong>{dq.scan_duration_seconds || 0}s</strong></span>
            <span>Data source: <strong>{ds}</strong></span>
            <span>Data status: <strong>{dataStatus}</strong></span>
            <span>Qual fails: <strong>{dq.qualifications_failed || 0}</strong></span>
          </div>
        </details>
      )}

      {/* ═══ PROVIDER FAILURE (page still renders) ═══════════════ */}
      {isUnavailable && !loading && (
        <div className="p-6 bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl text-center">
          <WifiOff className="w-8 h-8 text-amber-500 mx-auto mb-3" />
          <p className="font-semibold text-amber-700 dark:text-amber-300 text-sm">Market data temporarily unavailable</p>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Available data: {totalAnalyzed}/{totalEligible} holdings. The page remains usable with cached data.
          </p>
          <button onClick={() => loadSwing(true)} className="mt-4 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-[#1e293b] rounded-lg text-xs text-slate-600 dark:text-slate-300 font-medium">
            Retry Market Data
          </button>
        </div>
      )}

      {/* ═══ LOADING SKELETONS ═══════════════════════════════════ */}
      {loading && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-4 animate-pulse">
                <div className="h-3 w-16 bg-slate-200 dark:bg-slate-800 rounded mb-2" />
                <div className="h-6 w-10 bg-slate-200 dark:bg-slate-800 rounded" />
              </div>
            ))}
          </div>
          <div className="bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-6 text-center">
            <div className="animate-pulse space-y-2">
              <div className="h-4 w-56 bg-slate-200 dark:bg-slate-800 rounded mx-auto" />
              <div className="h-3 w-40 bg-slate-200 dark:bg-slate-800 rounded mx-auto" />
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-3 animate-pulse">
              Scanning {totalEligible || 25} holdings for technical setups...
            </p>
          </div>
        </div>
      )}

      {/* ═══ ERROR STATE ═════════════════════════════════════════ */}
      {error && !loading && (
        <div className="bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-6 text-center space-y-3">
          <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto" />
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Unable to Load Data</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">{error}</p>
          <button onClick={() => loadSwing(true)} className="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-[#1e293b] rounded-lg text-xs text-slate-600 dark:text-slate-300">
            Try Again
          </button>
        </div>
      )}

      {/* ═══ MAIN CONTENT (shows even during loading for tabs) ═══ */}
      {!loading && !error && (
        <>
          {/* ═══ SUMMARY CARDS ════════════════════════════════════ */}
          {tab === "swing" && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "Fresh Setups", count: freshCount, color: "emerald" },
                { label: "Developing", count: developingCount, color: "sky" },
                { label: "Watch", count: watchCount, color: "amber" },
                { label: "Invalidated", count: invalidatedCount, color: "rose" },
              ].map((c) => (
                <div key={c.label} className="bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{c.label}</p>
                  <p className={`text-2xl font-extrabold mt-1 text-${c.color}-600 dark:text-${c.color}-400`}>{c.count}</p>
                </div>
              ))}
            </div>
          )}

          {/* ═══ TABS ═════════════════════════════════════════════ */}
          <div className="flex items-center gap-1 bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-1">
            {([
              { id: "swing" as Tab, label: "Swing Opportunities", icon: TrendingUp },
              { id: "longterm" as Tab, label: "Long-Term", icon: BarChart3 },
              { id: "swaps" as Tab, label: "Portfolio Actions", icon: ArrowUpDown },
            ]).map((t) => {
              const Icon = t.icon;
              return (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`flex-1 flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
                    tab === t.id
                      ? "bg-sky-600 text-white shadow"
                      : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#0a0d14]"
                  }`}>
                  <Icon className="w-3.5 h-3.5" /><span className="hidden sm:inline">{t.label}</span>
                  <span className="sm:hidden">{t.id === "swing" ? "Swing" : t.id === "longterm" ? "Long" : "Actions"}</span>
                  {t.id === "swaps" && swapRecs.length > 0 && (
                    <span className="ml-1 px-1.5 py-0.5 text-[9px] bg-amber-500/20 text-amber-600 dark:text-amber-300 rounded-full">{swapRecs.length}</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* ════════════════════════════════════════════════════════ */}
          {/* SWING TAB                                              */}
          {/* ════════════════════════════════════════════════════════ */}
          {tab === "swing" && (
            <div className="space-y-4">
              {/* Sub-filters */}
              <div className="flex items-center gap-2 flex-wrap">
                {(["all", "fresh", "developing", "watch", "aging", "invalidated"] as SwingFilter[]).map((f) => (
                  <button key={f} onClick={() => setSwingFilter(f)}
                    className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors ${
                      swingFilter === f
                        ? "bg-sky-600 text-white border-sky-500"
                        : "bg-white dark:bg-[#121824] text-slate-500 border-slate-200 dark:border-[#1e293b] hover:text-slate-700 dark:hover:text-slate-200"
                    }`}>
                    {f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
                <span className="text-[11px] text-slate-500 ml-2">
                  {filteredOpps.length} of {swingOpps.length} setups
                </span>
              </div>

              {/* Zero-result experience */}
              {!isUnavailable && swingOpps.length === 0 && (
                <div className="p-8 bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl text-center">
                  <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto mb-3" />
                  <p className="font-semibold text-slate-700 dark:text-slate-200 text-sm">
                    No fresh actionable swing setups currently meet the required threshold
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-md mx-auto">
                    {totalEligible > 0
                      ? `${totalAnalyzed}/${totalEligible} eligible holdings were analyzed. Market conditions may simply not provide a high-quality entry right now.`
                      : "Analyzing your holdings for setups..."}
                  </p>
                  {dq.candidates_found > 0 && (
                    <p className="text-[11px] text-slate-500 mt-2">
                      {dq.candidates_found} setup patterns detected but did not meet quality threshold.
                    </p>
                  )}
                  {nearMisses.length > 0 && (
                    <div className="mt-6 space-y-2">
                      <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wide">Closest Candidates</p>
                      <div className="flex flex-wrap justify-center gap-2">
                        {nearMisses.map((nm: any) => (
                          <Link key={nm.symbol} href={`/stocks/${nm.symbol}`}
                            className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-[#1e293b] rounded-lg hover:border-sky-500/30 transition-colors">
                            <span className="text-xs font-bold text-slate-700 dark:text-slate-200">{nm.symbol}</span>
                            <span className="text-[10px] text-slate-500">{nm.score}/100</span>
                            <span className="text-[10px] text-slate-400">{nm.trend}</span>
                          </Link>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Opportunity cards */}
              {filteredOpps.map((op: any) => (
                <div key={op.symbol} className={`bg-white dark:bg-[#121824] border rounded-xl p-5 space-y-4 transition-colors ${
                  op.signal === "BUY" ? "border-emerald-500/30 hover:border-emerald-500/50" :
                  op.signal === "AVOID" ? "border-rose-500/20" : "border-slate-200 dark:border-[#1e293b] hover:border-slate-300 dark:hover:border-slate-700"
                }`}>
                  {/* Header row */}
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-3">
                      {op.display_rank && (
                        <span className="w-7 h-7 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20 flex items-center justify-center text-xs font-bold">
                          {op.display_rank}
                        </span>
                      )}
                      <div>
                        <Link href={`/stocks/${op.symbol}`} className="font-extrabold text-lg text-slate-900 dark:text-slate-100 hover:text-sky-600 dark:hover:text-sky-400 flex items-center space-x-2">
                          <span>{op.symbol}</span><ArrowRight className="w-4 h-4 text-sky-500" />
                        </Link>
                        <p className="text-xs text-slate-500">
                          {op.name} {op.sector && op.sector !== "Unknown" ? `· ${op.sector}` : ""}
                        </p>
                        {/* Source + Potential New Position */}
                        {universe !== "portfolio" && (
                          <div className="flex items-center gap-1.5 mt-0.5">
                            {op.source && (
                              <span className="px-1.5 py-0.5 text-[9px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 rounded border border-slate-200 dark:border-[#1e293b]">
                                {op.source}
                              </span>
                            )}
                            {!op.is_portfolio_holding && (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded border border-emerald-500/20">
                                Potential New Position
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {hasGoldenCross(op) && (
                        <span className="px-1.5 py-0.5 text-[9px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded border border-amber-500/20" title="Golden Cross Active">GC</span>
                      )}
                      <span className={`px-2.5 py-1 font-bold text-xs rounded-md border ${signalBadge(op.signal)}`}>{op.signal}</span>
                      <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${maturityBadge(op.maturity)}`}>{op.maturity}</span>
                      {op.freshness && (
                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${freshnessBadge(op.freshness)}`}>{op.freshness}</span>
                      )}
                    </div>
                  </div>

                  {/* Entry Status + Confidence */}
                  <div className="flex items-center gap-3 flex-wrap">
                    {op.entry_status && (
                      <span className={`px-2.5 py-1 text-[11px] font-semibold rounded border ${entryBadge(op.entry_status)}`}>
                        Entry: {entryStatusText(op.entry_status)}
                      </span>
                    )}
                    <span className="text-[11px] text-slate-500">
                      Confidence: <strong className="text-slate-700 dark:text-slate-300">{op.confidence}%</strong>
                    </span>
                    <span className="text-[11px] text-slate-500">
                      Score: <strong className="text-slate-700 dark:text-slate-300">{op.rank_score}/100</strong>
                    </span>
                    <button
                      onClick={() => setShowScoreDetail(showScoreDetail === op.symbol ? null : op.symbol)}
                      className="text-[11px] text-sky-600 dark:text-sky-400 hover:underline flex items-center gap-1"
                    >
                      <Info className="w-3 h-3" /> Why this score?
                    </button>
                  </div>

                  {/* Score Breakdown (expandable) */}
                  {showScoreDetail === op.symbol && op.score_breakdown && (
                    <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-lg border border-slate-200 dark:border-[#1e293b] space-y-1.5">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">Score Breakdown</span>
                        <button onClick={() => setShowScoreDetail(null)} className="text-slate-400 hover:text-slate-600">
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                      {Object.values(op.score_breakdown).map((b: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-[11px]">
                          <span className="w-24 text-slate-500">{b.label}</span>
                          <div className="flex-1 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${b.score / b.max > 0.6 ? "bg-emerald-500" : b.score / b.max > 0.3 ? "bg-amber-500" : "bg-rose-500"}`}
                              style={{ width: `${Math.min(100, (b.score / b.max) * 100)}%` }}
                            />
                          </div>
                          <span className="w-12 text-right font-mono text-slate-700 dark:text-slate-300">{b.score}/{b.max}</span>
                        </div>
                      ))}
                      <div className="pt-1.5 mt-1.5 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between text-[11px] font-bold">
                        <span className="text-slate-600 dark:text-slate-300">Overall</span>
                        <span className="text-slate-900 dark:text-slate-100">{op.rank_score}/100</span>
                      </div>
                    </div>
                  )}

                  {/* Prices + Targets */}
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-[11px]">
                    <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2.5">
                      <p className="text-slate-500">Current Price</p>
                      <p className="text-slate-900 dark:text-slate-200 font-bold">{fmt$(op.current_price)}</p>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2.5">
                      <p className="text-slate-500">Entry Zone</p>
                      <p className="text-slate-900 dark:text-slate-200 font-bold">{op.entry_zone?.support ? fmt$(op.entry_zone.support) : "N/A"}</p>
                    </div>
                    <div className="bg-emerald-50 dark:bg-emerald-500/5 rounded-lg p-2.5 border border-emerald-200 dark:border-emerald-500/10">
                      <p className="text-emerald-600 dark:text-emerald-400">Target</p>
                      <p className="text-emerald-700 dark:text-emerald-300 font-bold">{op.target_price ? fmt$(op.target_price) : "N/A"}</p>
                    </div>
                    <div className="bg-rose-50 dark:bg-rose-500/5 rounded-lg p-2.5 border border-rose-200 dark:border-rose-500/10">
                      <p className="text-rose-600 dark:text-rose-400">Stop</p>
                      <p className="text-rose-700 dark:text-rose-300 font-bold">{op.stop_price ? fmt$(op.stop_price) : "N/A"}</p>
                    </div>
                    <div className="bg-sky-50 dark:bg-sky-500/5 rounded-lg p-2.5 border border-sky-200 dark:border-sky-500/10">
                      <p className="text-sky-600 dark:text-sky-400">Risk/Reward</p>
                      <p className="text-sky-700 dark:text-sky-300 font-bold">{op.risk_reward ? `${op.risk_reward}:1` : "N/A"}</p>
                    </div>
                  </div>

                  {/* Technical Factors */}
                  {op.technical_factors?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {op.technical_factors.map((f: string, i: number) => (
                        <span key={i} className="px-2 py-0.5 text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 rounded border border-slate-200 dark:border-[#1e293b]">
                          {f}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Trend / Momentum / Volume / Risk / Horizon */}
                  <div className="flex items-center gap-3 flex-wrap text-[11px] text-slate-500">
                    <span>Trend: <strong className="text-slate-700 dark:text-slate-200">{op.trend}</strong></span>
                    <span>Momentum: <strong className="text-slate-700 dark:text-slate-200">{op.momentum || "N/A"}</strong></span>
                    <span>Risk: <strong className={
                      op.risk === "Low" ? "text-emerald-600 dark:text-emerald-400" :
                      op.risk === "High" || op.risk === "Elevated" ? "text-rose-600 dark:text-rose-400" :
                      "text-amber-600 dark:text-amber-400"
                    }>{op.risk}</strong></span>
                    {op.estimated_horizon && (
                      <span>Horizon: <strong className="text-slate-700 dark:text-slate-200">{op.estimated_horizon}</strong></span>
                    )}
                    {op.potential_upside != null && (
                      <span>Upside: <strong className="text-emerald-600 dark:text-emerald-400">+{op.potential_upside}%</strong></span>
                    )}
                    {op.late_entry_pct != null && op.late_entry_pct > 2 && (
                      <span className="text-amber-600 dark:text-amber-400">+{op.late_entry_pct}% since signal</span>
                    )}
                  </div>

                  {/* Why Now / Why Not */}
                  {op.why_now && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {op.why_now.why && (
                        <div className="flex items-start gap-2 p-2.5 bg-emerald-50 dark:bg-emerald-500/5 rounded-lg border border-emerald-200 dark:border-emerald-500/10">
                          <Zap className="w-3 h-3 text-emerald-500 dark:text-emerald-400 mt-0.5 shrink-0" />
                          <div>
                            <p className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">Why Now</p>
                            <p className="text-[11px] text-slate-600 dark:text-slate-300 mt-0.5">{op.why_now.why}</p>
                          </div>
                        </div>
                      )}
                      {op.why_now.why_not && (
                        <div className="flex items-start gap-2 p-2.5 bg-amber-50 dark:bg-amber-500/5 rounded-lg border border-amber-200 dark:border-amber-500/10">
                          <Clock className="w-3 h-3 text-amber-500 dark:text-amber-400 mt-0.5 shrink-0" />
                          <div>
                            <p className="text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wide">Why Not Now</p>
                            <p className="text-[11px] text-slate-600 dark:text-slate-300 mt-0.5">{op.why_now.why_not}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Portfolio Context */}
                  {op.portfolio_context && (op.portfolio_context.allocation_pct > 0 || op.portfolio_context.unrealized_gain_pct != null) && (
                    <div className="flex items-center gap-4 text-[11px] text-slate-500 pt-2 border-t border-slate-200 dark:border-[#1e293b]">
                      {op.portfolio_context.allocation_pct > 0 && (
                        <span>Allocation: <strong className="text-slate-700 dark:text-slate-300">{op.portfolio_context.allocation_pct.toFixed(1)}%</strong></span>
                      )}
                      {op.portfolio_context.unrealized_gain_pct != null && (
                        <span>P/L: <strong className={op.portfolio_context.unrealized_gain_pct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}>
                          {fmtPct(op.portfolio_context.unrealized_gain_pct)}
                        </strong></span>
                      )}
                      {op.portfolio_context.current_value != null && (
                        <span>Value: <strong className="text-slate-700 dark:text-slate-300">{fmt$(op.portfolio_context.current_value)}</strong></span>
                      )}
                    </div>
                  )}

                  {/* News */}
                  {op.news_items?.length > 0 && !op.news_unavailable && (
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">News / Catalyst</p>
                      {op.news_items.slice(0, 2).map((n: any, i: number) => (
                        <div key={i} className="flex items-start gap-2 text-[11px]">
                          <span className="text-slate-400 shrink-0">{n.source || "Source"}</span>
                          <span className="text-slate-600 dark:text-slate-300 line-clamp-1">{n.headline}</span>
                          {n.published_at && (
                            <span className="text-slate-400 shrink-0">{relativeTime(n.published_at)}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {op.news_unavailable && (
                    <p className="text-[11px] text-slate-400 italic">News unavailable — technical setup calculated independently.</p>
                  )}

                  {/* Footer: timestamps */}
                  <div className="flex items-center justify-between text-[10px] text-slate-400 pt-2 border-t border-slate-200 dark:border-[#1e293b]">
                    <span>Setup: {op.setup}</span>
                    {op.last_updated && (
                      <span title={`Generated: ${formatExact(op.last_updated)}`}>
                        Updated {relativeTime(op.last_updated)}
                      </span>
                    )}
                  </div>
                </div>
              ))}

              {/* Near-misses below cards */}
              {nearMisses.length > 0 && filteredOpps.length > 0 && (
                <div className="p-4 bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl">
                  <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wide mb-2">Closest Candidates</p>
                  <div className="flex flex-wrap gap-2">
                    {nearMisses.map((nm: any) => (
                      <Link key={nm.symbol} href={`/stocks/${nm.symbol}`}
                        className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-[#1e293b] rounded-lg hover:border-sky-500/30 transition-colors">
                        <span className="text-xs font-bold text-slate-700 dark:text-slate-200">{nm.symbol}</span>
                        <span className="text-[10px] text-slate-500">{nm.score}/100</span>
                        <span className="text-[10px] text-slate-400">{nm.trend}</span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ════════════════════════════════════════════════════════ */}
          {/* LONG-TERM TAB                                          */}
          {/* ════════════════════════════════════════════════════════ */}
          {tab === "longterm" && (
            <div className="space-y-4">
              <p className="text-[11px] text-slate-500">
                Fundamental quality scores based on earnings, growth, valuation, profitability, and financial health.
              </p>
              {longTermOpps.length === 0 ? (
                <div className="p-8 bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl text-center">
                  <BarChart3 className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                  <p className="text-xs text-slate-500">Loading long-term analysis...</p>
                </div>
              ) : (
                longTermOpps.map((op: any) => (
                  <div key={op.symbol} className="bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-3">
                        <Link href={`/stocks/${op.symbol}`} className="font-extrabold text-lg text-slate-900 dark:text-slate-100 hover:text-sky-600 dark:hover:text-sky-400 flex items-center space-x-2">
                          <span>{op.symbol}</span><ArrowRight className="w-4 h-4 text-sky-500" />
                        </Link>
                        <div>
                          <p className="text-xs text-slate-500">{op.name}</p>
                          <p className="text-[10px] text-slate-400">{op.sector}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`px-2.5 py-1 font-bold text-xs rounded border ${actionBadge(op.action)}`}>{op.action}</span>
                        <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-100 dark:bg-slate-500/10 text-slate-500 dark:text-slate-400 rounded border border-slate-200 dark:border-slate-500/20">
                          Score: {op.fundamental_score}/100
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                      <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2">
                        <p className="text-slate-500">Price</p>
                        <p className="text-slate-900 dark:text-slate-200 font-bold">{fmt$(op.current_price)}</p>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2">
                        <p className="text-slate-500">P/L</p>
                        <p className={`font-bold ${op.unrealized_gain_pct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                          {fmtPct(op.unrealized_gain_pct)}
                        </p>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2">
                        <p className="text-slate-500">Allocation</p>
                        <p className="text-slate-900 dark:text-slate-200 font-bold">{op.allocation_pct?.toFixed(1)}%</p>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2">
                        <p className="text-slate-500">Grade</p>
                        <p className="text-slate-900 dark:text-slate-200 font-bold">{op.fundamental_grade}</p>
                      </div>
                    </div>
                    {op.strengths?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {op.strengths.slice(0, 3).map((s: string, i: number) => (
                          <span key={i} className="px-2 py-0.5 text-[10px] bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded border border-emerald-200 dark:border-emerald-500/20">{s}</span>
                        ))}
                      </div>
                    )}
                    {op.weaknesses?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {op.weaknesses.slice(0, 2).map((w: string, i: number) => (
                          <span key={i} className="px-2 py-0.5 text-[10px] bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 rounded border border-rose-200 dark:border-rose-500/20">{w}</span>
                        ))}
                      </div>
                    )}
                    {op.recommendation && <p className="text-[11px] text-slate-500">{op.recommendation}</p>}
                  </div>
                ))
              )}
            </div>
          )}

          {/* ════════════════════════════════════════════════════════ */}
          {/* PORTFOLIO ACTIONS (SWAPS) TAB                          */}
          {/* ════════════════════════════════════════════════════════ */}
          {tab === "swaps" && (
            <div className="space-y-4">
              <p className="text-[11px] text-slate-500">
                When a holding becomes weaker or less suitable, these recommendations suggest potential replacements and explain why.
              </p>
              {swapRecs.length === 0 ? (
                <div className="p-8 bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl text-center">
                  <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto mb-3" />
                  <p className="font-semibold text-slate-700 dark:text-slate-200 text-sm">No swap recommendations</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">All holdings appear suitable for the portfolio. No replacements recommended.</p>
                </div>
              ) : (
                swapRecs.map((swap: any, idx: number) => (
                  <div key={swap.source_holding} className="bg-white dark:bg-[#121824] border border-slate-200 dark:border-[#1e293b] rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-3">
                        <span className="w-7 h-7 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 flex items-center justify-center text-xs font-bold">{idx + 1}</span>
                        <div>
                          <p className="text-[10px] text-slate-500 uppercase tracking-wide font-semibold">
                            {swap.action === "REDUCE" ? "Consider Reducing" : "Review Position"}
                          </p>
                          <Link href={`/stocks/${swap.source_holding}`} className="font-extrabold text-lg text-slate-900 dark:text-slate-100 hover:text-sky-600 dark:hover:text-sky-400 flex items-center space-x-2">
                            <span>{swap.source_holding}</span><ArrowRight className="w-4 h-4 text-sky-500" />
                          </Link>
                          <p className="text-xs text-slate-500">{swap.source_name} {swap.source_sector !== "Unknown" ? `· ${swap.source_sector}` : ""}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${actionBadge(swap.action)}`}>{swap.action}</span>
                        <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-100 dark:bg-slate-500/10 text-slate-500 dark:text-slate-400 rounded border border-slate-200 dark:border-slate-500/20">{swap.confidence}</span>
                      </div>
                    </div>

                    {swap.flags?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {swap.flags.map((f: any, i: number) => (
                          <span key={i} className={`px-2 py-0.5 text-[10px] rounded border ${
                            f.severity === "high"
                              ? "bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-500/20"
                              : "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/20"
                          }`}>{f.detail}</span>
                        ))}
                      </div>
                    )}

                    {swap.replacement_symbol && (
                      <div className="p-3 bg-emerald-50 dark:bg-emerald-500/5 rounded-lg border border-emerald-200 dark:border-emerald-500/10 space-y-2">
                        <div className="flex items-center gap-2">
                          <ArrowRight className="w-3 h-3 text-emerald-500 dark:text-emerald-400" />
                          <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold uppercase tracking-wide">Potential Replacement</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <Link href={`/stocks/${swap.replacement_symbol}`} className="font-bold text-slate-900 dark:text-slate-100 hover:text-sky-600 dark:hover:text-sky-400 flex items-center space-x-1">
                            <span>{swap.replacement_symbol}</span><ArrowRight className="w-3 h-3 text-sky-500" />
                          </Link>
                          <span className="text-xs text-slate-500">{swap.replacement_name}</span>
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded">Score: {swap.replacement_score}</span>
                        </div>
                        {swap.improvement_score > 0 && (
                          <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold">
                            +{swap.improvement_score} improvement over current holding
                          </p>
                        )}
                      </div>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                      <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2.5">
                        <p className="text-slate-500 font-semibold mb-1">Why reduce {swap.source_holding}?</p>
                        <p className="text-slate-600 dark:text-slate-300">{swap.fundamental_reason}</p>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2.5">
                        <p className="text-slate-500 font-semibold mb-1">Portfolio Impact</p>
                        <p className="text-slate-600 dark:text-slate-300">{swap.portfolio_impact}</p>
                        {swap.diversification_reason && <p className="text-slate-400 mt-1">{swap.diversification_reason}</p>}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
