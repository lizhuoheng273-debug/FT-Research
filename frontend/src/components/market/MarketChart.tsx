import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { EChart } from "@/components/ui/EChart";
import { api, type ChartPeriod, type MarketChart as MarketChartData } from "@/lib/api";
import { cn } from "@/lib/utils";

const periods: { key: ChartPeriod; label: string }[] = [
  { key: "intraday", label: "分时" }, { key: "five_day", label: "五日" },
  { key: "daily", label: "日K" }, { key: "weekly", label: "周K" }, { key: "monthly", label: "月K" },
];
const red = "#ef4444";
const green = "#22c55e";

const isTradingTime = () => {
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  return now.getDay() > 0 && now.getDay() < 6 && ((minutes >= 570 && minutes <= 690) || (minutes >= 780 && minutes <= 900));
};

function movingAverage(values: number[], size: number) {
  return values.map((_, index) => {
    if (index + 1 < size) return "-";
    const slice = values.slice(index + 1 - size, index + 1);
    return Number((slice.reduce((sum, value) => sum + value, 0) / size).toFixed(2));
  });
}

function chartOption(data: MarketChartData) {
  const points = data.points;
  const labels = points.map((point) => point.time.length > 10 ? point.time.slice(5, 16) : point.time.slice(5));
  if (data.period === "intraday" || data.period === "five_day") {
    const averages = points.map((point) => point.average);
    const validAverages = averages.filter((value) => Number.isFinite(value));
    const series: Array<Record<string, unknown>> = [
      { name: "现价", type: "line", data: points.map((point) => point.close), smooth: true, showSymbol: false, lineStyle: { color: red, width: 2 }, itemStyle: { color: red } },
    ];
    if (data.asset === "stock" && validAverages.length > 0) {
      series.push({ name: "均价", type: "line", data: averages, smooth: true, showSymbol: false, lineStyle: { color: "#f59e0b", type: "dashed" } });
    }
    return {
      animation: false,
      grid: { left: 48, right: 18, top: 24, bottom: 30 },
      tooltip: { trigger: "axis", axisPointer: { type: "cross" }, valueFormatter: (value: number) => value?.toFixed?.(2) ?? "—" },
      xAxis: { type: "category", data: labels, boundaryGap: false, axisLabel: { color: "#94a3b8", hideOverlap: true } },
      yAxis: [{ type: "value", scale: true, axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#33415555" } } }],
      series,
    };
  }
  const candles = points.map((point) => [point.open, point.close, point.low, point.high]);
  const closes = points.map((point) => point.close);
  return {
    animation: false,
    axisPointer: { link: [{ xAxisIndex: "all" }], label: { backgroundColor: "#64748b" } },
    grid: [{ left: 48, right: 18, top: 24, height: "62%" }, { left: 48, right: 18, top: "72%", height: "18%" }],
    tooltip: {
      trigger: "axis", axisPointer: { type: "cross" },
      formatter: (params: Array<{ dataIndex: number; seriesName: string; value: unknown }>) => {
        const index = params[0]?.dataIndex ?? 0;
        const point = points[index];
        if (!point) return "";
        return `${point.time}<br/>开 ${point.open.toFixed(2)}　高 ${point.high.toFixed(2)}　低 ${point.low.toFixed(2)}　收 ${point.close.toFixed(2)}<br/>量 ${point.volume.toLocaleString()}　额 ${point.amount.toLocaleString()}`;
      },
    },
    xAxis: [
      { type: "category", data: labels, boundaryGap: true, axisLabel: { color: "#94a3b8", hideOverlap: true }, axisPointer: { show: true } },
      { type: "category", data: labels, gridIndex: 1, boundaryGap: true, axisLabel: { show: false } },
    ],
    yAxis: [
      { type: "value", scale: true, axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "#33415555" } } },
      { type: "value", gridIndex: 1, splitNumber: 2, axisLabel: { color: "#94a3b8" }, splitLine: { show: false } },
    ],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }, { type: "slider", xAxisIndex: [0, 1], height: 16, bottom: 2, borderColor: "#334155" }],
    series: [
      { name: "K线", type: "candlestick", data: candles, itemStyle: { color: red, color0: green, borderColor: red, borderColor0: green } },
      { name: "MA5", type: "line", data: movingAverage(closes, 5), showSymbol: false, lineStyle: { color: "#f59e0b", width: 1.2 } },
      { name: "MA10", type: "line", data: movingAverage(closes, 10), showSymbol: false, lineStyle: { color: "#38bdf8", width: 1.2 } },
      { name: "MA20", type: "line", data: movingAverage(closes, 20), showSymbol: false, lineStyle: { color: "#a78bfa", width: 1.2 } },
      { name: "MA60", type: "line", data: movingAverage(closes, 60), showSymbol: false, lineStyle: { color: "#f472b6", width: 1.2 } },
      { name: "成交量", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: points.map((point) => ({ value: point.volume, itemStyle: { color: point.close >= point.open ? `${red}99` : `${green}99` } })) },
    ],
  };
}

interface Props { asset: "stock" | "index"; code: string; onData?: (data: MarketChartData | null) => void }

export function MarketChart({ asset, code, onData }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const fromUrl = searchParams.get("period");
  const initialPeriod: ChartPeriod = periods.some((item) => item.key === fromUrl) ? fromUrl as ChartPeriod : "intraday";
  const [period, setPeriod] = useState<ChartPeriod>(initialPeriod);
  const [data, setData] = useState<MarketChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(() => typeof document === "undefined" || document.visibilityState === "visible");
  const requestIdRef = useRef(0);

  const load = async (reset = false) => {
    const requestId = ++requestIdRef.current;
    if (reset) { setData(null); onData?.(null); }
    setLoading(true); setError(null);
    try {
      const next = await api.marketChart(asset, code, period);
      if (requestId !== requestIdRef.current) return;
      setData(next); onData?.(next);
    } catch (reason) {
      if (requestId === requestIdRef.current) setError(reason instanceof Error ? reason.message : "图表数据暂不可用");
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    void load(true);
    return () => { requestIdRef.current += 1; };
  }, [asset, code, period]);
  useEffect(() => {
    const next = searchParams.get("period");
    const restored: ChartPeriod = periods.some((item) => item.key === next) ? next as ChartPeriod : "intraday";
    setPeriod((current) => current === restored ? current : restored);
  }, [searchParams]);
  useEffect(() => {
    const onVisibility = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);
  useEffect(() => {
    if (!visible || !["intraday", "five_day"].includes(period) || !isTradingTime()) return;
    const timer = window.setInterval(() => { if (document.visibilityState === "visible" && isTradingTime()) void load(); }, 15_000);
    return () => window.clearInterval(timer);
  }, [asset, code, period, visible]);

  const option = useMemo(() => data ? chartOption(data) : null, [data]);
  return <div className="rounded-xl border border-border/60 bg-muted/10 p-3 sm:p-4">
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex min-w-0 flex-1 flex-wrap gap-1 rounded-lg bg-muted/30 p-1">
        {periods.map((item) => <button key={item.key} onClick={() => {
          const next = new URLSearchParams(searchParams);
          if (item.key === "intraday") next.delete("period"); else next.set("period", item.key);
          setSearchParams(next, { replace: true });
          setPeriod(item.key);
        }} className={cn("rounded-md px-3 py-1.5 text-xs", period === item.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>{item.label}</button>)}
      </div>
      <button onClick={() => void load()} disabled={loading} className="rounded-md p-2 text-muted-foreground hover:text-primary" title="刷新图表"><RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /></button>
    </div>
    {data?.stale && <p className="mt-2 text-xs text-warning">当前为最近一次真实行情缓存，可能已过期。</p>}
    {error && <p className="mt-3 flex items-center gap-1 text-xs text-warning"><AlertCircle className="h-3.5 w-3.5" />{error} · 可点击刷新重试</p>}
    {option ? <EChart option={option} height={390} /> : <div className="flex h-[390px] items-center justify-center text-sm text-muted-foreground">{loading ? "图表加载中…" : "暂无图表数据"}</div>}
    <p className="mt-2 text-[11px] text-muted-foreground/60">来源：{data?.source || "—"} · 更新时间：{data?.fetchedAt ? new Date(data.fetchedAt).toLocaleString("zh-CN") : "—"}{data?.stale ? " · 缓存/过期" : ""}</p>
  </div>;
}
