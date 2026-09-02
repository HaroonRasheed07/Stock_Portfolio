"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, X, Menu } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";

interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
  type: string;
  sector: string;
  market_cap: number;
}

export function Header({ onMenuToggle }: { onMenuToggle?: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [searching, setSearching] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSearchInput = (value: string) => {
    setQuery(value);
    setSelectedIndex(-1);
    
    if (debounceRef.current) clearTimeout(debounceRef.current);
    
    if (value.trim().length >= 1) {
      debounceRef.current = setTimeout(async () => {
        setSearching(true);
        try {
          const data = await fetchAPI<SearchResult[]>(`/stocks/search?q=${encodeURIComponent(value.trim())}`);
          setResults(data || []);
          setShowDropdown(true);
        } catch {
          setResults([]);
        } finally {
          setSearching(false);
        }
      }, 300);
    } else {
      setResults([]);
      setShowDropdown(false);
    }
  };

  const selectResult = (symbol: string) => {
    setQuery("");
    setShowDropdown(false);
    setResults([]);
    router.push(`/stocks/${symbol}`);
    inputRef.current?.blur();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showDropdown || results.length === 0) return;
    
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, -1));
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      selectResult(results[selectedIndex].symbol);
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      selectResult(query.trim().toUpperCase());
    }
  };

  return (
    <header className="h-16 border-b border-[#1e293b] bg-[#0a0d14]/80 backdrop-blur-md sticky top-0 z-40 px-4 md:px-8 flex items-center justify-between">
      <form onSubmit={handleSubmit} className="relative w-full md:w-96" ref={containerRef as any}>
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleSearchInput(e.target.value)}
          onFocus={() => results.length > 0 && setShowDropdown(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search by ticker or company name (e.g. AAPL, Apple)"
          className="w-full bg-[#121824] border border-[#1e293b] rounded-lg pl-9 pr-9 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/50"
        />
        {query && (
          <button
            type="button"
            onClick={() => { setQuery(""); setResults([]); setShowDropdown(false); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}

        {showDropdown && (results.length > 0 || searching) && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-[#121824] border border-[#1e293b] rounded-lg shadow-xl overflow-hidden z-50 max-h-80 overflow-y-auto">
            {searching && results.length === 0 ? (
              <div className="p-3 text-xs text-slate-400 text-center">Searching...</div>
            ) : (
              results.map((r, idx) => (
                <button
                  key={r.symbol}
                  type="button"
                  onClick={() => selectResult(r.symbol)}
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
      </form>

      <div className="flex items-center space-x-3 text-xs text-slate-400">
        {onMenuToggle && (
          <button onClick={onMenuToggle} className="lg:hidden text-slate-400 hover:text-slate-200 p-1">
            <Menu className="w-5 h-5" />
          </button>
        )}
        <ThemeToggle />
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span className="hidden sm:inline">Local Engine Active</span>
        </div>
      </div>
    </header>
  );
}
