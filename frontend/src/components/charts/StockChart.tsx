"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, CandlestickSeries } from "lightweight-charts";

interface StockChartProps {
  data: Array<{ date: string; open: number; high: number; low: number; close: number }>;
}

const THEMES = {
  dark: {
    background: "#121824",
    textColor: "#94a3b8",
    grid: "#1e293b",
    up: "#22c55e",
    down: "#ef4444",
    crosshair: "#94a3b8",
  },
  light: {
    background: "#ffffff",
    textColor: "#5c6d85",
    grid: "#e8ecf3",
    up: "#0d7a4a",
    down: "#c42b1c",
    crosshair: "#5c6d85",
  },
};

function currentTheme(): "dark" | "light" {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.classList.contains("light") ? "light" : "dark";
}

export function StockChart({ data }: StockChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chartContainerRef.current || !data || data.length === 0) return;

    const t = THEMES[currentTheme()];

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: t.background },
        textColor: t.textColor,
      },
      grid: {
        vertLines: { color: t.grid },
        horzLines: { color: t.grid },
      },
      crosshair: {
        vertLine: { color: t.crosshair, width: 1, style: 2, labelBackgroundColor: currentTheme() === "light" ? "#e4f0fb" : "#1e293b" },
        horzLine: { color: t.crosshair, width: 1, style: 2, labelBackgroundColor: currentTheme() === "light" ? "#e4f0fb" : "#1e293b" },
      },
      width: chartContainerRef.current.clientWidth,
      height: 350,
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: t.up,
      downColor: t.down,
      borderVisible: false,
      wickUpColor: t.up,
      wickDownColor: t.down,
    });

    const formattedData = data
      .filter((d) => d.date && d.open != null && d.high != null && d.low != null && d.close != null)
      .map((d) => ({
        time: d.date.split("T")[0],
        open: Number(d.open),
        high: Number(d.high),
        low: Number(d.low),
        close: Number(d.close),
      }))
      .sort((a, b) => (a.time as string).localeCompare(b.time as string))
      .filter((item, index, arr) =>
        index === 0 || item.time !== arr[index - 1].time
      );

    if (formattedData.length === 0) return;

    candlestickSeries.setData(formattedData as any);
    chart.timeScale().fitContent();

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener("resize", handleResize);

    // Re-render chart when the theme class changes on <html>
    const observer = new MutationObserver(() => {
      const nt = THEMES[currentTheme()];
      const isLight = currentTheme() === "light";
      chart.applyOptions({
        layout: { background: { type: ColorType.Solid, color: nt.background }, textColor: nt.textColor },
        grid: { vertLines: { color: nt.grid }, horzLines: { color: nt.grid } },
        crosshair: {
          vertLine: { color: nt.crosshair, labelBackgroundColor: isLight ? "#e4f0fb" : "#1e293b" },
          horzLine: { color: nt.crosshair, labelBackgroundColor: isLight ? "#e4f0fb" : "#1e293b" },
        },
      });
      candlestickSeries.applyOptions({
        upColor: nt.up,
        downColor: nt.down,
        wickUpColor: nt.up,
        wickDownColor: nt.down,
      });
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => {
      window.removeEventListener("resize", handleResize);
      observer.disconnect();
      chart.remove();
    };
  }, [data]);

  return <div ref={chartContainerRef} className="w-full h-[350px] rounded-xl border border-[#1e293b] overflow-hidden bg-[#121824]" />;
}
