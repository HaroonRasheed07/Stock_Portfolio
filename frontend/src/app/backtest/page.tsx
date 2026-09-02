"use client";

import { useState } from "react";
import { fetchAPI } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Activity, Play, CheckCircle, AlertTriangle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [strategy, setStrategy] = useState("sma_crossover");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRunBacktest = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    try {
      setLoading(true);
      const res = await fetchAPI<any>("/analytics/backtest", {
        method: "POST",
        body: JSON.stringify({
          symbol: symbol.toUpperCase(),
          strategy,
          initial_capital: 10000.0,
        }),
      });
      setResult(res);
    } catch (err: any) {
      const msg = err?.message || "Backtest failed";
      if (msg.includes("400")) {
        setError("Invalid ticker or insufficient historical data. Please check the symbol and try again.");
      } else if (msg.includes("429") || msg.includes("Too Many")) {
        setError("Market data provider is temporarily busy. Please wait a moment and try again.");
      } else {
        setError("Backtest failed: " + msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto px-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Historical Strategy Backtesting</h1>
        <p className="text-xs text-slate-400 mt-1">Simulate technical trading strategies on historical price data without look-ahead bias</p>
      </div>

      <form onSubmit={handleRunBacktest} className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-semibold text-slate-400 mb-1">Ticker Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="e.g. AAPL"
            className="bg-[#0a0d14] border border-[#1e293b] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-sky-500/50"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-400 mb-1">Strategy</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="bg-[#0a0d14] border border-[#1e293b] rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-sky-500/50"
          >
            <option value="sma_crossover">20/50 SMA Crossover</option>
            <option value="rsi_reversal">RSI Mean Reversal (&lt;30 Buy / &gt;70 Sell)</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={loading || !symbol.trim()}
          className="px-5 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center space-x-2 transition-colors"
        >
          <Play className="w-3.5 h-3.5" />
          <span>{loading ? "Running Backtest..." : "Run Backtest"}</span>
        </button>
      </form>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-6 text-center space-y-4">
          <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
          <h3 className="text-sm font-bold text-rose-200">Backtest Error</h3>
          <p className="text-xs text-slate-400">{error}</p>
        </div>
      )}

      {result && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Total Return</span>
              <p className={`text-xl font-bold mt-1 ${result.total_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {formatPercent(result.total_return)}
              </p>
            </div>

            <div className="p-4 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Win Rate</span>
              <p className="text-xl font-bold text-slate-100 mt-1">{result.win_rate}%</p>
            </div>

            <div className="p-4 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Max Drawdown</span>
              <p className="text-xl font-bold text-rose-400 mt-1">{result.max_drawdown}%</p>
            </div>

            <div className="p-4 bg-[#0a0d14] rounded-lg border border-[#1e293b]">
              <span className="text-xs text-slate-400">Total Trades</span>
              <p className="text-xl font-bold text-slate-100 mt-1">{result.num_trades}</p>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-bold text-slate-200 mb-3">Equity Growth Curve ($10,000 Starting Capital)</h3>
            <div className="h-64 border border-[#1e293b] rounded-lg p-2 bg-[#0a0d14]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result.equity_curve}>
                  <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 10 }} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={{ backgroundColor: "#0a0d14", borderColor: "#1e293b", color: "#f8fafc" }} />
                  <Line type="monotone" dataKey="equity" stroke="#0284c7" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
