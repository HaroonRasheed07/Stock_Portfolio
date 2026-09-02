"use client";

import { useEffect, useRef, useState } from "react";
import { fetchAPI } from "@/lib/api";
import { ShieldCheck, CheckCircle, AlertTriangle, RefreshCw, ArrowUpCircle, ArrowDownCircle, Target } from "lucide-react";

const severityColor = (s: string) =>
  s === "high"
    ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
    : s === "medium"
    ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
    : "bg-slate-500/10 text-slate-400 border-slate-500/20";

const priorityColor = (p: string) =>
  p === "high"
    ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
    : p === "medium"
    ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
    : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";

const gradeColor = (g: string) =>
  g === "A"
    ? "text-emerald-400"
    : g === "B"
    ? "text-sky-400"
    : g === "C"
    ? "text-amber-400"
    : "text-rose-400";

export default function HealthPage() {
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadPhase, setLoadPhase] = useState("Initializing...");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    setLoadPhase("Fetching portfolio holdings...");

    try {
      setLoadPhase("Calculating risk and diversification...");
      const data = await fetchAPI<any>("/analytics/portfolio-health");
      if (mountedRef.current) setReport(data);
    } catch (err: any) {
      if (!mountedRef.current) return;
      const msg = err?.message || "Failed to load health report";
      if (msg.includes("429") || msg.includes("Too Many")) {
        setError("Market data provider is temporarily busy. Please wait a moment and try again.");
      } else if (msg.includes("timeout") || msg.includes("Timeout")) {
        setError("Request timed out. The analysis is taking longer than expected. Please try again.");
      } else {
        setError("Could not generate health report. Ensure portfolio has holdings and try again.");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  return (
    <div className="space-y-8 max-w-4xl mx-auto px-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Portfolio Health Report</h1>
          <p className="text-xs text-slate-400 mt-1">Rule-based AI assessment of risk, diversification, and holding quality</p>
        </div>
        <button
          onClick={loadReport}
          disabled={loading}
          className="flex items-center space-x-2 px-3 py-2 bg-[#121824] hover:bg-slate-800 border border-[#1e293b] rounded-lg text-xs text-slate-300 font-medium"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Regenerate Report</span>
        </button>
      </div>

      {loading ? (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-8 text-center space-y-4">
          <div className="animate-pulse space-y-3">
            <div className="h-4 w-48 bg-slate-800 rounded mx-auto"></div>
            <div className="h-3 w-64 bg-slate-800 rounded mx-auto"></div>
            <div className="h-3 w-40 bg-slate-800 rounded mx-auto"></div>
          </div>
          <p className="text-xs text-slate-400 animate-pulse">{loadPhase}</p>
          <p className="text-[11px] text-slate-500">This may take 15-30 seconds on first load</p>
        </div>
      ) : error ? (
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-6 text-center space-y-4">
          <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
          <h3 className="text-sm font-bold text-rose-200">Unable to Load Report</h3>
          <p className="text-xs text-slate-400">{error}</p>
          <button
            onClick={loadReport}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg border border-slate-700 text-slate-200"
          >
            Try Again
          </button>
        </div>
      ) : !report ? (
        <div className="p-6 text-center text-xs text-slate-500">Could not generate health report. Ensure portfolio has holdings.</div>
      ) : (
        <div className="space-y-6">
          {/* ── Health Score + Grade ──────────────────────── */}
          <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-4">
              <div>
                <span className="text-xs text-slate-400 font-medium">Overall Health Score</span>
                <p className="text-3xl font-extrabold text-slate-100 mt-1">{report.overall_score}/100</p>
              </div>
              {report.grade && (
                <div className={`text-4xl font-extrabold ${gradeColor(report.grade)}`}>
                  {report.grade}
                </div>
              )}
            </div>
            <div className="flex items-center gap-3">
              {report.data_quality && (
                <span
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                    report.data_quality.completeness_pct >= 90
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : report.data_quality.completeness_pct >= 60
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                  }`}
                  title={
                    report.data_quality.missing_history?.length
                      ? `Missing history: ${report.data_quality.missing_history.join(", ")}`
                      : "All holdings analyzed"
                  }
                >
                  {report.data_quality.message}
                </span>
              )}
            </div>
          </div>

          {/* ── Executive Summary ──────────────────────── */}
          {report.executive_summary && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6">
              <h3 className="text-sm font-bold text-slate-200 mb-3">Executive Summary</h3>
              <p className="text-xs text-slate-300 leading-relaxed">{report.executive_summary}</p>
            </div>
          )}

          {/* ── Strengths ──────────────────────────────── */}
          {report.strengths && report.strengths.length > 0 && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-3">
              <h3 className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                <CheckCircle className="w-4 h-4" /> Strengths
              </h3>
              <div className="space-y-2">
                {report.strengths.map((s: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 p-3 bg-emerald-500/5 rounded-lg border border-emerald-500/10">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-semibold text-slate-200">{s.label}</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">{s.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Risks ───────────────────────────────────── */}
          {report.risks && report.risks.length > 0 && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-3">
              <h3 className="text-sm font-bold text-amber-400 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> Risks Detected
              </h3>
              <div className="space-y-2">
                {report.risks.map((r: any, i: number) => (
                  <div key={i} className={`flex items-start gap-3 p-3 rounded-lg border ${severityColor(r.severity)}`}>
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-semibold">{r.label}</p>
                      <p className="text-[11px] opacity-80 mt-0.5">{r.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── What Should I Do? ─────────────────────── */}
          {report.what_should_i_do && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-3">
              <h3 className="text-sm font-bold text-sky-400 flex items-center gap-2">
                <Target className="w-4 h-4" /> What Should I Do?
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">{report.what_should_i_do.summary}</p>

              {report.what_should_i_do.high_priority_actions?.length > 0 && (
                <div className="mt-3">
                  <p className="text-[11px] font-bold text-rose-400 mb-2 uppercase tracking-wide">High Priority</p>
                  {report.what_should_i_do.high_priority_actions.map((a: any, i: number) => (
                    <div key={i} className="flex items-start gap-3 p-3 bg-rose-500/5 rounded-lg border border-rose-500/10 mb-2">
                      <ArrowUpCircle className="w-3.5 h-3.5 text-rose-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-xs font-semibold text-slate-200">{a.action}</p>
                        <p className="text-[11px] text-slate-400 mt-0.5">{a.reason}</p>
                        {a.estimated_impact && (
                          <p className="text-[11px] text-emerald-400 mt-0.5">Impact: {a.estimated_impact}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {report.what_should_i_do.medium_priority_actions?.length > 0 && (
                <div className="mt-3">
                  <p className="text-[11px] font-bold text-amber-400 mb-2 uppercase tracking-wide">Medium Priority</p>
                  {report.what_should_i_do.medium_priority_actions.map((a: any, i: number) => (
                    <div key={i} className="flex items-start gap-3 p-3 bg-amber-500/5 rounded-lg border border-amber-500/10 mb-2">
                      <ArrowDownCircle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-xs font-semibold text-slate-200">{a.action}</p>
                        <p className="text-[11px] text-slate-400 mt-0.5">{a.reason}</p>
                        {a.estimated_impact && (
                          <p className="text-[11px] text-emerald-400 mt-0.5">Impact: {a.estimated_impact}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {report.what_should_i_do.next_review && (
                <p className="text-[11px] text-slate-500 mt-2 italic">{report.what_should_i_do.next_review}</p>
              )}
            </div>
          )}

          {/* ── Strong & Weak Holdings ─────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {report.strong_holdings && report.strong_holdings.length > 0 && (
              <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5 space-y-3">
                <h3 className="text-xs font-bold text-emerald-400 uppercase tracking-wide">Top Performers</h3>
                {report.strong_holdings.map((h: any, i: number) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-emerald-500/5 rounded-lg">
                    <div>
                      <p className="text-xs font-bold text-slate-200">{h.symbol}</p>
                      <p className="text-[11px] text-slate-400">{h.name}</p>
                    </div>
                    <p className="text-xs font-bold text-emerald-400">{h.unrealized_gain_pct > 0 ? "+" : ""}{h.unrealized_gain_pct}%</p>
                  </div>
                ))}
              </div>
            )}

            {report.weak_holdings && report.weak_holdings.length > 0 && (
              <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-5 space-y-3">
                <h3 className="text-xs font-bold text-rose-400 uppercase tracking-wide">Lagging Positions</h3>
                {report.weak_holdings.map((h: any, i: number) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-rose-500/5 rounded-lg">
                    <div>
                      <p className="text-xs font-bold text-slate-200">{h.symbol}</p>
                      <p className="text-[11px] text-slate-400">{h.name}</p>
                    </div>
                    <p className="text-xs font-bold text-rose-400">{h.unrealized_gain_pct > 0 ? "+" : ""}{h.unrealized_gain_pct}%</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Per-Holding Recommendations ────────────── */}
          {report.per_holding_recommendations && report.per_holding_recommendations.length > 0 && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-4">
              <h3 className="text-sm font-bold text-sky-400">Per-Holding Recommendations</h3>
              <div className="space-y-3">
                {report.per_holding_recommendations.map((rec: any, i: number) => (
                  <div key={i} className={`p-3 rounded-lg border ${
                    rec.recommendation === "REDUCE" ? "bg-rose-500/5 border-rose-500/20" :
                    rec.recommendation === "WATCH" ? "bg-amber-500/5 border-amber-500/20" :
                    rec.recommendation === "INCREASE" ? "bg-emerald-500/5 border-emerald-500/20" :
                    "bg-slate-500/5 border-[#1e293b]"
                  }`}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-200">{rec.symbol}</span>
                        <span className="text-[10px] text-slate-400">{rec.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {rec.technical_score != null && (
                          <span className="text-[10px] text-sky-400">Tech: {rec.technical_score}</span>
                        )}
                        {rec.fundamental_score != null && (
                          <span className="text-[10px] text-emerald-400">Fund: {rec.fundamental_score}</span>
                        )}
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          rec.recommendation === "REDUCE" ? "bg-rose-500/20 text-rose-400" :
                          rec.recommendation === "WATCH" ? "bg-amber-500/20 text-amber-400" :
                          rec.recommendation === "INCREASE" ? "bg-emerald-500/20 text-emerald-400" :
                          "bg-slate-500/20 text-slate-400"
                        }`}>
                          {rec.recommendation}
                        </span>
                      </div>
                    </div>
                    <p className="text-[11px] text-slate-300 leading-relaxed">{rec.reasoning}</p>
                    {rec.technical_summary && (
                      <p className="text-[10px] text-slate-500 mt-1">{rec.technical_summary}</p>
                    )}
                    {rec.fundamental_summary && (
                      <p className="text-[10px] text-slate-500">{rec.fundamental_summary}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Full Report (fallback) ─────────────────── */}
          {report.full_report && (
            <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-4">
              <h3 className="text-sm font-bold text-slate-200">Full Report</h3>
              <pre className="whitespace-pre-wrap font-sans text-xs text-slate-300 leading-relaxed bg-[#0a0d14] p-4 rounded-lg border border-[#1e293b]">
                {report.full_report}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
