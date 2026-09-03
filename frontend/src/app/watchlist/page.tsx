"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Plus, Trash2, AlertTriangle, RefreshCw, Search } from "lucide-react";

interface Suggestion {
  symbol: string;
  name: string;
  type: string;
}

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<any[]>([]);
  const [symbol, setSymbol] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [searching, setSearching] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const containerRef = useRef<HTMLFormElement>(null);

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

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  const skipSuggestions = useCallback((sym: string) => {
    const upper = sym.toUpperCase();
    return watchlist.some((w) => (w.symbol || "").toUpperCase() === upper);
  }, [watchlist]);

  const handleSearchInput = (value: string) => {
    setSymbol(value);
    setSelectedIndex(-1);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = value.trim();
    if (trimmed.length >= 1) {
      debounceRef.current = setTimeout(async () => {
        setSearching(true);
        try {
          const data = await fetchAPI<Suggestion[]>(`/stocks/search?q=${encodeURIComponent(trimmed)}`);
          const filtered = (data || []).filter((r) => !skipSuggestions(r.symbol));
          setSuggestions(filtered);
          setShowDropdown(true);
        } catch {
          setSuggestions([]);
        } finally {
          setSearching(false);
        }
      }, 300);
    } else {
      setSuggestions([]);
      setShowDropdown(false);
    }
  };

  const autoFill = (sym: string) => {
    setSymbol(sym.toUpperCase());
    setSuggestions([]);
    setShowDropdown(false);
    setSelectedIndex(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showDropdown || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, -1));
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      autoFill(suggestions[selectedIndex].symbol);
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

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

        <form onSubmit={handleAdd} className="relative flex items-center" ref={containerRef}>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={symbol}
              onChange={(e) => handleSearchInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
              placeholder="Add ticker (e.g. NVDA)..."
              className="bg-[#121824] border border-[#1e293b] rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/50 w-56"
              autoComplete="off"
            />
            {showDropdown && (suggestions.length > 0 || searching) && (
              <div className="absolute top-full left-0 mt-1 w-72 bg-[#121824] border border-[#1e293b] rounded-lg shadow-xl overflow-hidden z-50 max-h-72 overflow-y-auto">
                {searching && suggestions.length === 0 ? (
                  <div className="p-3 text-xs text-slate-400 text-center">Searching...</div>
                ) : (
                  suggestions.map((r, idx) => (
                    <button
                      key={r.symbol}
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => autoFill(r.symbol)}
                      className={`w-full px-4 py-3 text-left flex items-center justify-between hover:bg-sky-500/10 transition-colors ${
                        idx === selectedIndex ? "bg-sky-500/10" : ""
                      }`}
                    >
                      <div>
                        <span className="font-bold text-sm text-sky-400">{r.symbol}</span>
                        <span className="text-xs text-slate-400 ml-2">{r.name}</span>
                      </div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">
                        {r.type === "ETF" ? "ETF" : r.type === "EQUITY" ? "Stock" : r.type}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
          <button type="submit" className="ml-2 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold flex items-center space-x-1">
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
