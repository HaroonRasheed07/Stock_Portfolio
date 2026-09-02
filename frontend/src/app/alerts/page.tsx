"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchAPI } from "@/lib/api";
import {
  Bell,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  Clock,
  ExternalLink,
  Trash2,
  Filter,
  Zap,
  Briefcase,
  Eye,
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

interface CatalystAlert {
  id: string;
  symbol: string;
  title: string;
  message: string;
  alert_type: string;
  impact_level: string;
  catalyst_type: string;
  sentiment_label: string;
  price_reaction?: number;
  volume_ratio?: number;
  is_holding?: boolean;
  is_watchlist?: boolean;
  relevance_reason?: string;
  is_read: boolean;
  created_at: string;
  source?: string;
  url?: string;
}

export default function AlertsPage() {
  const [catalystAlerts, setCatalystAlerts] = useState<CatalystAlert[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loadingCatalyst, setLoadingCatalyst] = useState(true);

  const [alertRules, setAlertRules] = useState<any>({ rules: [], history: [] });
  const [loadingRules, setLoadingRules] = useState(true);

  const loadCatalystAlerts = useCallback(async () => {
    try {
      const data = await fetchAPI<{ alerts: CatalystAlert[]; unread_count: number }>(
        "/catalysts/alerts"
      );
      setCatalystAlerts(data.alerts || []);
      setUnreadCount(data.unread_count || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingCatalyst(false);
    }
  }, []);

  const loadAlertRules = useCallback(async () => {
    try {
      const data = await fetchAPI<any>("/alerts");
      setAlertRules(data || { rules: [], history: [] });
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingRules(false);
    }
  }, []);

  useEffect(() => {
    loadCatalystAlerts();
    loadAlertRules();
  }, [loadCatalystAlerts, loadAlertRules]);

  const handleMarkAllRead = async () => {
    try {
      await fetchAPI("/catalysts/alerts/read-all", { method: "POST" });
      setCatalystAlerts((prev) => prev.map((a) => ({ ...a, is_read: true })));
      setUnreadCount(0);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDismiss = async (alertId: string) => {
    try {
      await fetchAPI(`/catalysts/alerts/${alertId}/dismiss`, { method: "POST" });
      setCatalystAlerts((prev) => prev.filter((a) => a.id !== alertId));
      setUnreadCount((prev) => {
        const dismissed = catalystAlerts.find((a) => a.id === alertId);
        return dismissed && !dismissed.is_read ? Math.max(0, prev - 1) : prev;
      });
    } catch (err) {
      console.error(err);
    }
  };

  const getAlertIcon = (alertType: string) => {
    switch (alertType) {
      case "positive_catalyst":
        return <TrendingUp className="w-4 h-4 text-emerald-400" />;
      case "negative_catalyst":
        return <AlertTriangle className="w-4 h-4 text-rose-400" />;
      default:
        return <Bell className="w-4 h-4 text-sky-400" />;
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-slate-100 flex items-center space-x-2">
          <Bell className="w-6 h-6 text-sky-400" />
          <span>Alerts & Notifications</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Each alert is a significant news catalyst (earnings, analyst actions, legal events, product news) tied to the specific company it is about. Alerts marked <span className="text-emerald-400 font-semibold">HOLDING</span> directly affect companies in your portfolio; others are market-wide events shown for awareness. No buy/sell action is implied — always review the underlying article.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-[#121824] border border-[#1e293b] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[#1e293b] flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                  <Zap className="w-4 h-4 text-sky-400" />
                  <span>Catalyst Alerts</span>
                </h3>
                {unreadCount > 0 && (
                  <span className="px-2 py-0.5 bg-sky-500/20 text-sky-400 text-[11px] font-bold rounded-full border border-sky-500/30">
                    {unreadCount} unread
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="px-3 py-1.5 text-[11px] font-semibold text-sky-400 hover:text-sky-300 bg-sky-500/10 hover:bg-sky-500/20 rounded-lg border border-sky-500/20 transition-colors flex items-center space-x-1.5"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>Mark All Read</span>
                </button>
              )}
            </div>

            <div className="divide-y divide-[#1e293b]">
              {loadingCatalyst ? (
                <div className="p-8 text-center">
                  <div className="text-xs text-slate-400 animate-pulse">
                    Loading catalyst alerts...
                  </div>
                </div>
              ) : catalystAlerts.length === 0 ? (
                <div className="p-8 text-center">
                  <Bell className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                  <p className="text-xs text-slate-500">
                    No catalyst alerts yet. Catalyst events will generate alerts here.
                  </p>
                </div>
              ) : (
                catalystAlerts.map((alert) => {
                  const impactStyle =
                    IMPACT_STYLES[alert.impact_level] || IMPACT_STYLES.LOW;
                  const sentimentStyle =
                    SENTIMENT_STYLES[alert.sentiment_label] ||
                    SENTIMENT_STYLES.neutral;
                  const catalystLabel =
                    CATALYST_TYPE_LABELS[alert.catalyst_type] ||
                    alert.catalyst_type ||
                    "";

                  return (
                    <div
                      key={alert.id}
                      className={`p-4 hover:bg-[#0a0d14]/50 transition-colors ${
                        !alert.is_read ? "border-l-2 border-l-sky-500" : ""
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start space-x-3 flex-1 min-w-0">
                          <div className="mt-0.5 flex-shrink-0">
                            {getAlertIcon(alert.alert_type)}
                          </div>
                          <div className="flex-1 min-w-0 space-y-1.5">
                            <div className="flex items-center flex-wrap gap-2">
                              <span className="font-bold text-sm text-sky-400">
                                {alert.symbol}
                              </span>
                              <span
                                className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded border ${impactStyle}`}
                              >
                                {alert.impact_level}
                              </span>
                              {catalystLabel && (
                                <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded border bg-[#0a0d14] text-slate-400 border-[#1e293b]">
                                  {catalystLabel}
                                </span>
                              )}
                              {alert.sentiment_label && (
                                <span
                                  className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded border ${sentimentStyle}`}
                                >
                                  {alert.sentiment_label}
                                </span>
                              )}
                            </div>
                            <p className="text-xs font-semibold text-slate-200">
                              {alert.title}
                            </p>
                            <p className="text-xs text-slate-400 line-clamp-2">
                              {alert.message}
                            </p>
                            {alert.relevance_reason && (
                              <p className="text-[11px] text-slate-500 flex items-center gap-1.5">
                                <span className={`px-1.5 py-0.5 rounded font-bold uppercase text-[10px] ${
                                  alert.is_holding
                                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                    : "bg-[#121824] text-slate-400 border border-[#1e293b]"
                                }`}>
                                  {alert.is_holding ? "HOLDING" : "MARKET"}
                                </span>
                                {alert.relevance_reason}
                              </p>
                            )}
                            <div className="flex items-center flex-wrap gap-3 text-[11px] text-slate-500">
                              <span className="flex items-center space-x-1">
                                <Clock className="w-3 h-3" />
                                <span>{timeAgo(alert.created_at)}</span>
                              </span>
                              {alert.price_reaction !== undefined &&
                                alert.price_reaction !== null && (
                                  <span
                                    className={`font-semibold ${
                                      alert.price_reaction >= 0
                                        ? "text-emerald-400"
                                        : "text-rose-400"
                                    }`}
                                  >
                                    {alert.price_reaction >= 0 ? "+" : ""}
                                    {(alert.price_reaction * 100).toFixed(1)}%
                                  </span>
                                )}
                              {alert.volume_ratio !== undefined &&
                                alert.volume_ratio !== null && (
                                  <span className="text-amber-400 font-semibold">
                                    {alert.volume_ratio.toFixed(1)}× avg
                                  </span>
                                )}
                              {alert.source && (
                                <span className="flex items-center space-x-1">
                                  <ExternalLink className="w-3 h-3" />
                                  <span>{alert.source}</span>
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={() => handleDismiss(alert.id)}
                          className="flex-shrink-0 p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
                          title="Dismiss"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        <div className="lg:col-span-1">
          <div className="bg-[#121824] border border-[#1e293b] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[#1e293b]">
              <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                <Filter className="w-4 h-4 text-slate-400" />
                <span>Alert Rules</span>
              </h3>
              <p className="text-[11px] text-slate-500 mt-1">
                System-defined price and volatility thresholds
              </p>
            </div>

            <div className="p-4">
              {loadingRules ? (
                <div className="text-xs text-slate-400 animate-pulse py-4 text-center">
                  Loading alert rules...
                </div>
              ) : alertRules.rules.length === 0 ? (
                <p className="text-xs text-slate-500 py-4 text-center">
                  No active alert rules. Default system risk alerts are active.
                </p>
              ) : (
                <div className="space-y-2">
                  {alertRules.rules.map((rule: any) => (
                    <div
                      key={rule.id}
                      className="p-3 bg-[#0a0d14] rounded-lg border border-[#1e293b] space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-sky-400">
                          {rule.symbol || "PORTFOLIO"}
                        </span>
                        <span className="text-[10px] font-bold text-emerald-400 uppercase">
                          Active
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400">
                        {rule.alert_type} ({rule.condition} {rule.threshold})
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
