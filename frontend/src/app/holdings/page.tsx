"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Search, ArrowUpDown, ExternalLink, Sparkles } from "lucide-react";

export default function HoldingsPage() {
  const [holdings, setHoldings] = useState<any[]>([]);
  const [catalystMap, setCatalystMap] = useState<Record<string, any>>({});
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAPI<any[]>("/portfolio/holdings")
      .then(async (data) => {
        setHoldings(data || []);
        // Fetch sentiment for all holdings in parallel
        const symbols = (data || []).map((h: any) => h.symbol);
        const map: Record<string, any> = {};
        await Promise.all(
          symbols.map(async (sym: string) => {
            try {
              const cat = await fetchAPI<any>(`/catalysts/sentiment/${sym}`);
              map[sym] = cat;
            } catch {}
          })
        );
        setCatalystMap(map);
      })
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  const filtered = holdings.filter(
    (h) =>
      h.symbol.toLowerCase().includes(filter.toLowerCase()) ||
      (h.name && h.name.toLowerCase().includes(filter.toLowerCase())) ||
      (h.sector && h.sector.toLowerCase().includes(filter.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Holdings Inventory</h1>
          <p className="text-xs text-slate-400 mt-1">Detailed list of portfolio positions with valuation metrics</p>
        </div>
        <div className="relative w-full sm:w-64 flex-shrink-0">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter holdings..."
            className="w-full bg-[#121824] border border-[#1e293b] rounded-lg pl-9 pr-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-sky-500/50"
          />
        </div>
      </div>

      {/* Mobile hint */}
      <p className="text-[11px] text-slate-500 sm:hidden">Swipe horizontally to see all columns →</p>

      <div className="bg-[#121824] border border-[#1e293b] rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-400 animate-pulse">Loading holdings inventory...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left text-slate-300" style={{ minWidth: "900px" }}>
              <thead className="bg-[#0a0d14] text-slate-400 uppercase border-b border-[#1e293b]">
                <tr>
                  <th className="p-3.5">Symbol</th>
                  <th className="p-3.5">Company Name</th>
                  <th className="p-3.5 text-right">Shares</th>
                  <th className="p-3.5 text-right">Price</th>
                  <th className="p-3.5 text-right">Market Value</th>
                  <th className="p-3.5 text-right">Cost Basis</th>
                  <th className="p-3.5 text-right">Unrealized Gain</th>
                  <th className="p-3.5 text-right">Return %</th>
                  <th className="p-3.5 text-right">Allocation</th>
                  <th className="p-3.5 text-center">Sentiment</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e293b]">
                {filtered.map((h) => (
                  <tr key={h.symbol} className="hover:bg-slate-800/40">
                    <td className="p-3.5 font-bold text-sky-400">
                      <Link href={`/stocks/${h.symbol}`} className="hover:underline flex items-center space-x-1">
                        <span>{h.symbol}</span>
                        <ExternalLink className="w-3 h-3 text-slate-500" />
                      </Link>
                    </td>
                    <td className="p-3.5 text-slate-200 max-w-[200px] truncate">{h.name || "-"}</td>
                    <td className="p-3.5 text-right">{h.quantity ? h.quantity.toFixed(4) : "-"}</td>
                    <td className="p-3.5 text-right font-medium text-slate-200">
                      {formatCurrency(h.current_price)}
                    </td>
                    <td className="p-3.5 text-right font-bold text-slate-100">
                      {formatCurrency(h.current_value)}
                    </td>
                    <td className="p-3.5 text-right text-slate-400">
                      {h.cost_basis ? formatCurrency(h.cost_basis) : "-"}
                    </td>
                    <td className={`p-3.5 text-right font-semibold ${h.unrealized_gain >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {h.unrealized_gain !== null ? formatCurrency(h.unrealized_gain) : "-"}
                    </td>
                    <td className={`p-3.5 text-right font-semibold ${h.unrealized_gain_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {h.unrealized_gain_pct !== null ? formatPercent(h.unrealized_gain_pct) : "-"}
                    </td>
                    <td className="p-3.5 text-right font-medium text-slate-300">
                      {h.allocation_pct !== null ? `${h.allocation_pct}%` : "-"}
                    </td>
                    <td className="p-3.5 text-center">
                      {catalystMap[h.symbol] ? (
                        <span className={`text-xs font-semibold px-2 py-1 rounded ${
                          catalystMap[h.symbol].overall_sentiment === "Positive"
                            ? "bg-emerald-500/10 text-emerald-400"
                            : catalystMap[h.symbol].overall_sentiment === "Negative"
                            ? "bg-rose-500/10 text-rose-400"
                            : "bg-slate-500/10 text-slate-400"
                        }`}>
                          {catalystMap[h.symbol].overall_sentiment || "Neutral"}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
