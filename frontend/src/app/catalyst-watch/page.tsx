"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchAPI } from "@/lib/api";
import {
  Zap,
  TrendingUp,
  AlertTriangle,
  Filter,
  RefreshCw,
  Clock,
  Eye,
  Briefcase,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Bell,
} from "lucide-react";

const CATALYST_TYPE_LABELS: Record<string, string> = {
  clinical_trial: "Clinical Trial",
  fda_approval: "FDA Approval",
  fda_rejection: "FDA Rejection",
  earnings_release: "Earnings",
  guidance_change: "Guidance",
  merger_acquisition: "M&A",
  major_contract: "Contract",
  product_launch: "Product Launch",
  insider_activity: "Insider Activity",
  management_change: "Management",
  analyst_action: "Analyst",
  regulatory_investigation: "Regulatory",
  legal_development: "Legal",
  dividend_action: "Dividend",
  stock_action: "Stock Action",
  macro_event: "Macro",
  institutional_activity: "Institutional",
};

const IMPACT_STYLES: Record<string, string> = {
  CRITICAL: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  HIGH: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  MEDIUM: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  LOW: "bg-slate-800 text-slate-400 border-slate-700",
};

const CATALYST_TYPES = [
  "clinical_trial",
  "fda_approval",
  "fda_rejection",
  "earnings_release",
  "guidance_change",
  "merger_acquisition",
  "major_contract",
  "product_launch",
  "insider_activity",
  "management_change",
  "analyst_action",
  "regulatory_investigation",
  "legal_development",
  "dividend_action",
  "stock_action",
  "macro_event",
  "institutional_activity",
];

function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return "Date unavailable";
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (isNaN(then)) return "Date unavailable";
  const diffMs = now - then;
  if (diffMs < 0) return "Just now";
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function CatalystWatchPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [watchStocks, setWatchStocks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [loadingWatch, setLoadingWatch] = useState(true);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [lastScanTime, setLastScanTime] = useState<string>("");

  const [impactFilter, setImpactFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [scopeFilter, setScopeFilter] = useState("all");

  const loadCatalysts = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (impactFilter !== "all") params.set("impact_level", impactFilter);
      if (typeFilter !== "all") params.set("catalyst_type", typeFilter);
      if (scopeFilter !== "all") params.set("scope", scopeFilter);
      params.set("limit", "100");

      const data = await fetchAPI<any[]>(`/catalysts/events?${params.toString()}`);
      setEvents(data || []);
      setLastUpdated(new Date().toISOString());
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [impactFilter, typeFilter, scopeFilter]);

  const loadWatch = useCallback(async () => {
    try {
      const data = await fetchAPI<any[]>("/catalysts/watch");
      setWatchStocks(data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingWatch(false);
    }
  }, []);

  useEffect(() => {
    loadCatalysts();
  }, [loadCatalysts]);

  useEffect(() => {
    loadWatch();
  }, [loadWatch]);

  const handleScanNow = async () => {
    setScanning(true);
    try {
      await fetchAPI("/catalysts/scan-market", { method: "POST" });
      setLastScanTime(new Date().toISOString());
      await loadCatalysts();
      await loadWatch();
    } catch (err) {
      console.error(err);
    } finally {
      setScanning(false);
    }
  };

  const now24h = new Date(Date.now() - 86400000);
  const catalysts24h = events.filter(
    (e) => e.published_at && new Date(e.published_at) >= now24h
  );
  const highImpact = events.filter((e) =>
    ["CRITICAL", "HIGH"].includes(e.impact_level)
  );
  const unreadAlerts = events.filter((e) => !e.read).length;
  const increasingAttention = watchStocks.filter(
    (s) => s.attention_trend === "increasing"
  ).length;

  const stats = [
    {
      label: "Catalysts 24h",
      value: catalysts24h.length,
      icon: Zap,
      color: "text-sky-400",
    },
    {
      label: "High Impact",
      value: highImpact.length,
      icon: AlertTriangle,
      color: "text-amber-400",
    },
    {
      label: "Unread Alerts",
      value: unreadAlerts,
      icon: Bell,
      color: "text-rose-400",
    },
    {
      label: "Increasing Attention",
      value: increasingAttention,
      icon: TrendingUp,
      color: "text-emerald-400",
    },
  ];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center space-x-2">
            <Zap className="w-6 h-6 text-sky-400" />
            <span>Catalyst Watch</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Monitor high-impact catalysts relevant to your portfolio and watchlist. Focused on upcoming earnings, FDA events, major contracts, and actionable company-specific announcements.
          </p>
          <div className="flex items-center space-x-3 mt-1">
            {lastScanTime && (
              <p className="text-xs text-slate-400 flex items-center space-x-1">
                <Clock className="w-3 h-3" />
                <span>Last checked: {timeAgo(lastScanTime)}</span>
              </p>
            )}
            {lastUpdated && (() => {
              const t = new Date(lastUpdated);
              return isNaN(t.getTime()) ? null : (
                <p className="text-xs text-slate-500">
                  Last updated: {t.toLocaleTimeString()}
                </p>
              );
            })()}
          </div>
        </div>
        <button
          onClick={handleScanNow}
          disabled={scanning}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center space-x-2 transition-colors"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${scanning ? "animate-spin" : ""}`}
          />
          <span>{scanning ? "Scanning..." : "Scan Now"}</span>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.label}
              className="bg-[#121824] border border-[#1e293b] rounded-xl p-4"
            >
              <div className="flex items-center space-x-2 mb-2">
                <Icon className={`w-4 h-4 ${stat.color}`} />
                <span className="text-[11px] text-slate-400 uppercase font-semibold">
                  {stat.label}
                </span>
              </div>
              <p className="text-2xl font-bold text-slate-100">{stat.value}</p>
            </div>
          );
        })}
      </div>

      {/* Filter Bar */}
      <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-4">
        <div className="flex items-center space-x-2 mb-3">
          <Filter className="w-4 h-4 text-slate-400" />
          <span className="text-xs font-semibold text-slate-300">Filters</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Impact Level */}
          <div>
            <label className="block text-[11px] text-slate-400 uppercase mb-1.5 font-semibold">
              Impact Level
            </label>
            <div className="flex flex-wrap gap-1.5">
              {["all", "CRITICAL", "HIGH", "MEDIUM"].map((level) => (
                <button
                  key={level}
                  onClick={() => setImpactFilter(level)}
                  className={`px-2.5 py-1 text-[11px] font-semibold rounded-md border transition-colors ${
                    impactFilter === level
                      ? level === "CRITICAL"
                        ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                        : level === "HIGH"
                          ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                          : level === "MEDIUM"
                            ? "bg-sky-500/10 text-sky-400 border-sky-500/30"
                            : "bg-sky-600 text-white border-sky-500"
                      : "bg-[#0a0d14] text-slate-400 border-[#1e293b] hover:border-slate-600"
                  }`}
                >
                  {level === "all" ? "All" : level}
                </button>
              ))}
            </div>
          </div>

          {/* Catalyst Type */}
          <div>
            <label className="block text-[11px] text-slate-400 uppercase mb-1.5 font-semibold">
              Catalyst Type
            </label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full bg-[#0a0d14] border border-[#1e293b] rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500/50"
            >
              <option value="all">All Types</option>
              {CATALYST_TYPES.map((t) => (
                <option key={t} value={t}>
                  {CATALYST_TYPE_LABELS[t] || t}
                </option>
              ))}
            </select>
          </div>

          {/* Scope */}
          <div>
            <label className="block text-[11px] text-slate-400 uppercase mb-1.5 font-semibold">
              Scope
            </label>
            <div className="flex flex-wrap gap-1.5">
              {[
                { value: "all", label: "All", icon: null },
                { value: "portfolio", label: "Portfolio", icon: Briefcase },
                { value: "watchlist", label: "Watchlist", icon: Eye },
              ].map((s) => {
                const SIcon = s.icon;
                return (
                  <button
                    key={s.value}
                    onClick={() => setScopeFilter(s.value)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-md border transition-colors flex items-center space-x-1 ${
                      scopeFilter === s.value
                        ? "bg-sky-600 text-white border-sky-500"
                        : "bg-[#0a0d14] text-slate-400 border-[#1e293b] hover:border-slate-600"
                    }`}
                  >
                    {SIcon && <SIcon className="w-3 h-3" />}
                    <span>{s.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Catalyst Events */}
      <div className="space-y-3">
        {loading ? (
          <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center">
            <div className="text-xs text-slate-400 animate-pulse">
              Loading catalysts...
            </div>
          </div>
        ) : events.length === 0 ? (
          <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center">
            <Zap className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-xs text-slate-500">
              No catalysts found. Try adjusting your filters or run a market
              scan.
            </p>
          </div>
        ) : (
          events.map((event, idx) => {
            const isExpanded = expandedIdx === idx;
            const impactStyle =
              IMPACT_STYLES[event.impact_level] || IMPACT_STYLES.LOW;
            const typeLabel =
              CATALYST_TYPE_LABELS[event.catalyst_type] ||
              event.catalyst_type ||
              "General";
            const hasHolding = event.affects_holding;
            const hasWatchlist = event.affects_watchlist;

            return (
              <div
                key={idx}
                className="bg-[#121824] border border-[#1e293b] rounded-xl overflow-hidden hover:border-slate-700 transition-colors"
              >
                {/* Main Row */}
                <button
                  onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                  className="w-full p-4 text-left flex items-start justify-between gap-4"
                >
                  <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex items-center flex-wrap gap-2">
                      <span className="font-bold text-sm text-sky-400 flex-shrink-0">
                        {event.symbol}
                      </span>
                      {hasHolding && (
                        <span className="flex items-center space-x-1 px-1.5 py-0.5 bg-emerald-500/10 text-emerald-400 text-[10px] font-bold uppercase rounded border border-emerald-500/20">
                          <Briefcase className="w-2.5 h-2.5" />
                          <span>Holding</span>
                        </span>
                      )}
                      {hasWatchlist && (
                        <span className="flex items-center space-x-1 px-1.5 py-0.5 bg-sky-500/10 text-sky-400 text-[10px] font-bold uppercase rounded border border-sky-500/20">
                          <Eye className="w-2.5 h-2.5" />
                          <span>Watchlist</span>
                        </span>
                      )}
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded border ${impactStyle}`}
                      >
                        {event.impact_level}
                      </span>
                      <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded border bg-[#0a0d14] text-slate-400 border-[#1e293b]">
                        {typeLabel}
                      </span>
                      {event.sentiment_label && (
                        <span
                          className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded border ${
                            event.sentiment_label === "positive"
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                              : event.sentiment_label === "negative"
                                ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                                : "bg-slate-800 text-slate-400 border-slate-700"
                          }`}
                        >
                          {event.sentiment_label}
                        </span>
                      )}
                      {event.relevance_score !== undefined && (
                        <span className="text-[10px] text-slate-500 font-semibold">
                          {Math.round(event.relevance_score * 100)}% relevant
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-200 line-clamp-2">
                      {event.headline || event.title || "No headline"}
                    </p>
                    <div className="flex items-center flex-wrap gap-3 text-[11px] text-slate-500">
                      {event.source && (
                        <span className="flex items-center space-x-1">
                          <ExternalLink className="w-3 h-3" />
                          <span>{event.source}</span>
                        </span>
                      )}
                      {event.published_at && (
                        <span className="flex items-center space-x-1">
                          <Clock className="w-3 h-3" />
                          <span>{timeAgo(event.published_at)}</span>
                        </span>
                      )}
                      {event.potential_impact && (
                        <span className="text-slate-400 italic">
                          {event.potential_impact}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex-shrink-0 mt-1">
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-slate-500" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-500" />
                    )}
                  </div>
                </button>

                {/* Expanded Detail */}
                {isExpanded && (
                  <div className="border-t border-[#1e293b] p-4 space-y-4 bg-[#0a0d14]">
                    {event.summary && (
                      <div>
                        <h4 className="text-[11px] text-slate-400 uppercase font-semibold mb-1">
                          Summary
                        </h4>
                        <p className="text-xs text-slate-300 leading-relaxed">
                          {event.summary}
                        </p>
                      </div>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {event.short_term_view && (
                        <div className="bg-[#121824] border border-[#1e293b] rounded-lg p-3">
                          <h4 className="text-[11px] text-sky-400 uppercase font-semibold mb-1.5 flex items-center space-x-1">
                            <Clock className="w-3 h-3" />
                            <span>Short-Term View</span>
                          </h4>
                          <p className="text-xs text-slate-300 leading-relaxed">
                            {event.short_term_view}
                          </p>
                        </div>
                      )}
                      {event.long_term_view && (
                        <div className="bg-[#121824] border border-[#1e293b] rounded-lg p-3">
                          <h4 className="text-[11px] text-emerald-400 uppercase font-semibold mb-1.5 flex items-center space-x-1">
                            <TrendingUp className="w-3 h-3" />
                            <span>Long-Term View</span>
                          </h4>
                          <p className="text-xs text-slate-300 leading-relaxed">
                            {event.long_term_view}
                          </p>
                        </div>
                      )}
                    </div>
                    {event.url && (
                      <a
                        href={event.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center space-x-1.5 text-[11px] text-sky-400 hover:text-sky-300 font-semibold"
                      >
                        <ExternalLink className="w-3 h-3" />
                        <span>Read full article</span>
                      </a>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Catalyst Watch Section */}
      <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span>Catalyst Watch</span>
          </h3>
          <span className="text-[11px] text-slate-500">
            Stocks with increasing attention
          </span>
        </div>
        {loadingWatch ? (
          <div className="text-xs text-slate-400 animate-pulse py-4 text-center">
            Loading watch data...
          </div>
        ) : watchStocks.length === 0 ? (
          <p className="text-xs text-slate-500 py-4 text-center">
            No catalyst watch data available yet.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {watchStocks.slice(0, 12).map((stock, idx) => {
              const isIncreasing = stock.attention_trend === "increasing";
              return (
                <div
                  key={idx}
                  className={`p-3 rounded-lg border ${
                    isIncreasing
                      ? "bg-emerald-500/5 border-emerald-500/20"
                      : "bg-[#0a0d14] border-[#1e293b]"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-xs text-sky-400">
                      {stock.symbol}
                    </span>
                    {isIncreasing && (
                      <span className="flex items-center space-x-1 text-[10px] text-emerald-400 font-bold">
                        <TrendingUp className="w-3 h-3" />
                        <span>Rising</span>
                      </span>
                    )}
                    {stock.early_catalyst_watch && (
                      <span className="flex items-center space-x-1 px-1.5 py-0.5 bg-purple-500/10 text-purple-400 text-[10px] font-bold rounded border border-purple-500/20">
                        <Zap className="w-3 h-3" />
                        <span>Early</span>
                      </span>
                    )}
                  </div>
                  {stock.company && (
                    <p className="text-[11px] text-slate-400 truncate mb-1">
                      {stock.company}
                    </p>
                  )}
                  <div className="flex items-center flex-wrap gap-2 text-[11px]">
                    {stock.news_frequency_7d > 0 && (
                      <span className="text-slate-400">
                        {stock.news_frequency_7d} articles/7d
                      </span>
                    )}
                    {stock.high_impact_count_7d > 0 && (
                      <span className="text-amber-400 font-semibold">
                        {stock.high_impact_count_7d} high-impact
                      </span>
                    )}
                    {stock.early_signal && (
                      <p className="text-[10px] text-emerald-400 italic w-full mt-1">
                        {stock.early_signal}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
