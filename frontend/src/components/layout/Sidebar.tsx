"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Briefcase, Table, Search, Eye,
  TrendingUp, Newspaper, Bell, Activity, FileText, Settings, Upload, Zap, X
} from "lucide-react";

const navItems = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Portfolio & Import", href: "/portfolio", icon: Briefcase },
  { name: "Holdings", href: "/holdings", icon: Table },
  { name: "Watchlist", href: "/watchlist", icon: Eye },
  { name: "Catalyst Watch", href: "/catalyst-watch", icon: Zap },
  { name: "Trading Opportunities", href: "/trading", icon: TrendingUp },
  { name: "News & Catalysts", href: "/news", icon: Newspaper },
  { name: "Alerts", href: "/alerts", icon: Bell },
  { name: "Backtesting", href: "/backtest", icon: Activity },
  { name: "Portfolio Health", href: "/health", icon: FileText },
  { name: "Rebalancing", href: "/rebalancing", icon: Briefcase },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-[#121824] border-r border-[#1e293b] flex flex-col h-screen sticky top-0">
      <div className="p-6 border-b border-[#1e293b] flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-sky-500/20 border border-sky-500/40 flex items-center justify-center text-sky-400 font-bold">
            P
          </div>
          <div>
            <h1 className="font-bold text-slate-100 text-sm tracking-wide">PORTFOLIO AI</h1>
            <p className="text-xs text-slate-400">Intelligence Platform</p>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="lg:hidden text-slate-400 hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onClose}
              className={`flex items-center space-x-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 ${
                isActive
                  ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 border border-transparent"
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? "text-sky-400" : ""}`} />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-[#1e293b] text-xs text-slate-500 text-center">
        v1.0.0 • Local Portfolio Intelligence
      </div>
    </aside>
  );
}
