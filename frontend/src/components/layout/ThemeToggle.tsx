"use client";

import { useState, useEffect } from "react";
import { Sun, Moon, Monitor } from "lucide-react";

type Theme = "dark" | "light" | "system";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const saved = (localStorage.getItem("theme") as Theme | null) || "dark";
    setTheme(saved);
    applyTheme(saved);
  }, []);

  const applyTheme = (t: Theme) => {
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    
    if (t === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.classList.add(prefersDark ? "dark" : "light");
    } else {
      root.classList.add(t);
    }
  };

  const cycleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : theme === "light" ? "system" : "dark";
    setTheme(next);
    localStorage.setItem("theme", next);
    applyTheme(next);
  };

  const icon = theme === "dark" ? <Moon className="w-4 h-4" /> : 
               theme === "light" ? <Sun className="w-4 h-4" /> : 
               <Monitor className="w-4 h-4" />;
  
  const label = theme === "dark" ? "Dark" : theme === "light" ? "Light" : "System";

  return (
    <button
      onClick={cycleTheme}
      className="flex items-center space-x-1.5 px-2 py-1.5 rounded-lg border border-[#1e293b] hover:bg-slate-800 text-xs text-slate-400 hover:text-slate-200 transition-colors"
      title={`Current: ${label}. Click to switch.`}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
