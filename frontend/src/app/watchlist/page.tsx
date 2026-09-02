"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Eye, Plus, Trash2, TrendingUp, AlertTriangle, RefreshCw } from "lucide-react";

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<any[]>([]);
  const [symbol, setSymbol] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; abortRef.current?.abort(); };
  }, []);

  const loadWatchlist = useCallback(async (retryCount = 0) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const reqId = ++requestIdRef.current;

    setLoading(true);
    setError(null);
    try {
      const data = await fetchAPI<any[]>("/watchlist", { signal: controller.signal } as any);
      if (!mountedRef.current || controller.signal.aborted || reqId !== requestIdRef.current) return;
      setWatchlist(data || []);
    } catch (err: any) {
      if (!mountedRef.current || controller.signal.aborted) return;
      const msg = err?.message || "";
      if (msg.includes("abort")) return;
      // Auto-retry once on network failure
      if (retryCount < 1 && (msg.includes("Failed to fetch") || msg.includes("NetworkError"))) {
        await new Promise(r => setTimeout(r, 1500));
        if (!mountedRef.current) return;
        return loadWatchlist(retryCount + 1);
      }
      console.error("Watchlist load error:", err);
      setError("Could not load watchlist. Market data may be temporarily unavailable.");
    } finally {
      if (mountedRef.current && !controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => { loadWatchlist(); }, [loadWatchlist]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol) return;
    try {
      await fetchAPI("/watchlist", {
        method: "POST",
        body: JSON.stringify({ symbol: symbol.toUpperCase() }),
      });
      setSymbol("");
      loadWatchlist();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleRemove = async (sym: string) => {
    try {
      await fetchAPI(`/watchlist/${sym}`, { method: "DELETE" });
      loadWatchlist();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Watchlist</h1>
          <p className="text-xs text-slate-400 mt-1">Track prospective large-cap companies for investment timing</p>
        </div>

        <form onSubmit={handleAdd} className="flex items-center space-x-2">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Add ticker (e.g. NVDA)..."
            className="bg-[#121824] border border-[#1e293b] rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500/50"
          />
          <button type="submit" className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold flex items-center space-x-1">
            <Plus className="w-3.5 h-3.5" />
            <span>Add</span>
          </button>
        </form>
      </div>

      <div className="bg-[#121824] border border-[#1e293b] rounded-xl overflow-hidden overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-400">Loading watchlist...</div>
        ) : error ? (
          <div className="p-8 text-center space-y-3">
            <AlertTriangle className="w-6 h-6 text-amber-400 mx-auto" />
            <p className="text-xs text-amber-300 font-semibold">{error}</p>
            <button
              onClick={() => loadWatchlist()}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-xs text-slate-200 font-medium flex items-center space-x-2 mx-auto"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry</span>
            </button>
          </div>
        ) : watchlist.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">No items on your watchlist yet. Add tickers above or choose from suggestions below.</div>
        ) : (
          <table className="w-full text-xs text-left text-slate-300">
            <thead className="bg-[#0a0d14] text-slate-400 uppercase border-b border-[#1e293b]">
              <tr>
                <th className="p-3.5">Symbol</th>
                <th className="p-3.5">Name</th>
                <th className="p-3.5 text-right">Price</th>
                <th className="p-3.5 text-right">Change</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]">
              {watchlist.map((item) => (
                <tr key={item.symbol} className="hover:bg-slate-800/40">
                  <td className="p-3.5 font-bold text-sky-400">
                    <Link href={`/stocks/${item.symbol}`} className="hover:underline">{item.symbol}</Link>
                  </td>
                  <td className="p-3.5 text-slate-300">{item.name || "-"}</td>
                  <td className="p-3.5 text-right font-medium text-slate-200">
                    {formatCurrency(item.current_price)}
                  </td>
                  <td className={`p-3.5 text-right font-semibold ${item.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {item.change_pct !== undefined ? formatPercent(item.change_pct) : "-"}
                  </td>
                  <td className="p-3.5 text-right">
                    <button
                      onClick={() => handleRemove(item.symbol)}
                      className="text-slate-500 hover:text-rose-400 transition-colors p-1"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
