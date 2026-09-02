"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchAPI } from "@/lib/api";
import {
  Newspaper,
  Zap,
  Briefcase,
  Filter,
  RefreshCw,
  Clock,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  AlertTriangle,
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

const SENTIMENT_STYLES: Record<string, string> = {
  positive: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  negative: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  neutral: "bg-slate-800 text-slate-400 border-slate-700",
};

type Tab = "portfolio" | "catalysts" | "all";

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

function formatExactTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true,
  });
}

function sentimentScoreDisplay(score: number | null | undefined): string {
  if (score == null) return "";
  const pct = Math.round(Math.abs(score) * 100);
  return `${pct}% ${score > 0 ? "pos" : score < 0 ? "neg" : "neu"}`;
}

export default function NewsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("portfolio");
  const [catalystEvents, setCatalystEvents] = useState<any[]>([]);
  const [rawNews, setRawNews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingNews, setLoadingNews] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [expandedIdx, setExpandedIdx] = useState<string | null>(null);
  const [lastScanTime, setLastScanTime] = useState<string>("");
  const [lastUpdated, setLastUpdated] = useState<string>("");

  const loadCatalysts = useCallback(async (scope?: string) => {
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (scope && scope !== "all") params.set("scope", scope);
      const data = await fetchAPI<any[]>(`/catalysts/events?${params.toString()}`);
      setCatalystEvents(data || []);
      setLastUpdated(new Date().toISOString());
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRawNews = useCallback(async () => {
    try {
      const data = await fetchAPI<any[]>("/stocks/SPY/news?limit=30");
      setRawNews(data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingNews(false);
    }
  }, []);

  useEffect(() => {
    loadCatalysts(activeTab === "portfolio" ? "portfolio" : undefined);
    if (activeTab === "all") {
      loadRawNews();
    }
  }, [activeTab]);

  const handleScanPortfolio = async () => {
    setScanning(true);
    try {
      await fetchAPI("/catalysts/scan-portfolio", { method: "POST" });
      setLastScanTime(new Date().toISOString());
      await loadCatalysts(activeTab === "portfolio" ? "portfolio" : undefined);
    } catch (err) {
      console.error(err);
    } finally {
      setScanning(false);
    }
  };

  const now24h = new Date(Date.now() - 86400000);
  const catalystsToday = catalystEvents.filter(
    (e) => e.published_at && new Date(e.published_at) >= now24h
  );
  const highImpactCount = catalystEvents.filter((e) =>
    ["CRITICAL", "HIGH"].includes(e.impact_level)
  ).length;
  const portfolioSymbolsWithNews = new Set(
    catalystEvents.filter((e) => e.affects_holding).map((e) => e.symbol)
  ).size;

  const displayEvents = catalystEvents;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center space-x-2">
            <Newspaper className="w-6 h-6 text-sky-400" />
            <span>News & Catalysts</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Discover market and company news that may affect your investments. Broad information feed covering earnings, analyst actions, contracts, and market events.
          </p>
          <div className="flex items-center space-x-3 mt-1">
            {lastScanTime && (
              <p className="text-[11px] text-slate-500 flex items-center space-x-1">
                <Clock className="w-3 h-3" />
                <span>Last scanned: {timeAgo(lastScanTime)}</span>
              </p>
            )}
            {lastUpdated && (() => {
              const t = new Date(lastUpdated);
              return isNaN(t.getTime()) ? null : (
                <p className="text-[11px] text-slate-500">
                  Updated: {t.toLocaleTimeString()}
                </p>
              );
            })()}
          </div>
        </div>
        <button
          onClick={handleScanPortfolio}
          disabled={scanning}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center space-x-2 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scanning ? "animate-spin" : ""}`} />
          <span>{scanning ? "Scanning..." : "Scan Portfolio"}</span>
        </button>
      </div>

      {/* Summary Bar */}
      <div className="grid grid-cols-3 gap-4">
        {[
          {
            label: "Catalysts Today",
            value: catalystsToday.length,
            icon: Zap,
            color: "text-sky-400",
          },
          {
            label: "High Impact",
            value: highImpactCount,
            icon: AlertTriangle,
            color: "text-amber-400",
          },
          {
            label: "Holdings With News",
            value: portfolioSymbolsWithNews,
            icon: Briefcase,
            color: "text-emerald-400",
          },
        ].map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className="bg-[#121824] border border-[#1e293b] rounded-xl p-4">
              <div className="flex items-center space-x-2 mb-2">
                <Icon className={`w-4 h-4 ${stat.color}`} />
                <span className="text-[11px] text-slate-400 uppercase font-semibold">{stat.label}</span>
              </div>
              <p className="text-2xl font-bold text-slate-100">{stat.value}</p>
            </div>
          );
        })}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-[#121824] border border-[#1e293b] rounded-xl p-1">
        {([
          { id: "portfolio" as Tab, label: "Portfolio News", icon: Briefcase },
          { id: "catalysts" as Tab, label: "Market Catalysts", icon: Zap },
          { id: "all" as Tab, label: "All News", icon: Newspaper },
        ]).map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
                isActive
                  ? "bg-sky-600 text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-[#0a0d14]"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Portfolio News & Market Catalysts Tabs */}
      {(activeTab === "portfolio" || activeTab === "catalysts") && (
        <div className="space-y-3">
          {loading ? (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center">
              <div className="text-xs text-slate-400 animate-pulse">Loading catalysts...</div>
            </div>
          ) : displayEvents.length === 0 ? (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center">
              <Zap className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-500">
                {activeTab === "portfolio"
                  ? "No catalysts affecting your portfolio holdings yet."
                  : "No catalyst events found."}
              </p>
            </div>
          ) : (
            displayEvents.map((event, idx) => {
              const eventKey = `${event.symbol}-${idx}`;
              const isExpanded = expandedIdx === eventKey;
              const impactStyle = IMPACT_STYLES[event.impact_level] || IMPACT_STYLES.LOW;
              const sentimentStyle =
                SENTIMENT_STYLES[event.sentiment_label] || SENTIMENT_STYLES.neutral;
              const typeLabel =
                CATALYST_TYPE_LABELS[event.catalyst_type] || event.catalyst_type || "General";

              return (
                <div
                  key={eventKey}
                  className="bg-[#121824] border border-[#1e293b] rounded-xl overflow-hidden hover:border-slate-700 transition-colors"
                >
                  <button
                    onClick={() => setExpandedIdx(isExpanded ? null : eventKey)}
                    className="w-full p-4 text-left flex items-start justify-between gap-4"
                  >
                    <div className="flex-1 min-w-0 space-y-2">
                      <div className="flex items-center flex-wrap gap-2">
                        <span className="font-bold text-sm text-sky-400 flex-shrink-0">
                          {event.symbol}
                        </span>
                        {event.affects_holding && (
                          <span className="flex items-center space-x-1 px-1.5 py-0.5 bg-emerald-500/10 text-emerald-400 text-[10px] font-bold uppercase rounded border border-emerald-500/20">
                            <Briefcase className="w-2.5 h-2.5" />
                            <span>Holding</span>
                          </span>
                        )}
                        <span className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded border ${impactStyle}`}>
                          {event.impact_level}
                        </span>
                        <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded border bg-[#0a0d14] text-slate-400 border-[#1e293b]">
                          {typeLabel}
                        </span>
                        {event.sentiment_label && (
                          <span className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded border ${sentimentStyle}`}>
                            {event.sentiment_label}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-200 line-clamp-2">
                        {event.headline || event.title || "No headline"}
                      </p>
                      {event.relevance_label && (
                        <p className="text-[11px] flex items-center flex-wrap gap-1.5">
                          <span className={`px-1.5 py-0.5 rounded font-bold uppercase text-[10px] ${
                            event.relevance_label === "DIRECT HOLDING"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : event.relevance_label === "WATCHLIST"
                              ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                              : "bg-[#121824] text-slate-400 border border-[#1e293b]"
                          }`}>
                            Why shown: {event.relevance_label}
                          </span>
                          <span className="text-slate-500">{event.relevance_reason}</span>
                        </p>
                      )}
                      <div className="flex items-center flex-wrap gap-3 text-[11px] text-slate-500">
                        {event.source && (
                          <span className="flex items-center space-x-1">
                            <ExternalLink className="w-3 h-3" />
                            <span>{event.source}</span>
                          </span>
                        )}
                        {event.published_at && (
                          <span className="flex items-center space-x-1" title={formatExactTime(event.published_at)}>
                            <Clock className="w-3 h-3" />
                            <span>{timeAgo(event.published_at)}</span>
                          </span>
                        )}
                        {event.potential_impact && (
                          <span className="text-slate-400 italic">{event.potential_impact}</span>
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

                  {isExpanded && (
                    <div className="border-t border-[#1e293b] p-4 space-y-4 bg-[#0a0d14]">
                      {event.summary && (
                        <div>
                          <h4 className="text-[11px] text-slate-400 uppercase font-semibold mb-1">
                            Summary
                          </h4>
                          <p className="text-xs text-slate-300 leading-relaxed">{event.summary}</p>
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
      )}

      {/* All News Tab */}
      {activeTab === "all" && (
        <div className="space-y-4">
          {loadingNews ? (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center">
              <div className="text-xs text-slate-400 animate-pulse">Fetching financial news feeds...</div>
            </div>
          ) : rawNews.length === 0 ? (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center">
              <Newspaper className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-500">No news articles found.</p>
            </div>
          ) : (
            rawNews.map((item, idx) => (
              <div
                key={idx}
                className="bg-[#121824] border border-[#1e293b] rounded-xl p-5 hover:border-slate-700 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold text-sm text-slate-200 hover:text-sky-400 flex items-center space-x-1.5"
                    >
                      <span>{item.title}</span>
                      <ExternalLink className="w-3.5 h-3.5 text-slate-500" />
                    </a>
                    {item.summary && (
                      <p className="text-xs text-slate-400 line-clamp-2">{item.summary}</p>
                    )}
                  </div>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded border flex-shrink-0 ${
                      SENTIMENT_STYLES[item.sentiment_label] || SENTIMENT_STYLES.neutral
                    }`}
                  >
                    {item.sentiment_label || "Neutral"}
                  </span>
                </div>
                <div className="flex items-center space-x-4 mt-3 text-[11px] text-slate-500">
                  <span className="flex items-center space-x-1">
                    <span className="text-slate-400 font-medium">{item.source || "yfinance"}</span>
                  </span>
                  {item.published_at && (
                    <span className="flex items-center space-x-1" title={formatExactTime(item.published_at)}>
                      <Clock className="w-3 h-3" />
                      <span>{timeAgo(item.published_at)}</span>
                    </span>
                  )}
                  {item.sentiment_score != null && (
                    <span className="text-slate-500">{sentimentScoreDisplay(item.sentiment_score)}</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
