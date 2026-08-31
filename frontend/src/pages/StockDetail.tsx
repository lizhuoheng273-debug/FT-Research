import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Star } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { GlassCard } from "@/components/ui/GlassCard";
import { MarketChart } from "@/components/market/MarketChart";
import { StockResearchTabs } from "@/components/stock/StockResearchTabs";
import { api, type Quote } from "@/lib/api";
import { addCodes, loadWatch, saveWatch } from "@/lib/watchlist";
import { cn } from "@/lib/utils";

const color = (value: number) => value > 0 ? "text-danger" : value < 0 ? "text-success" : "text-muted-foreground";
const money = (value: number) => value >= 1e8 ? `${(value / 1e8).toFixed(2)} 亿` : value >= 1e4 ? `${(value / 1e4).toFixed(2)} 万` : value.toLocaleString();
const volume = (hands: number) => hands >= 1e4 ? `${(hands / 1e4).toFixed(2)} 万手` : `${hands.toLocaleString()} 手`;
const pct = (value: number) => `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;

function isTradingTime(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Shanghai", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(now);
  const read = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value || "";
  if (["Sat", "Sun"].includes(read("weekday"))) return false;
  const minutes = Number(read("hour")) * 60 + Number(read("minute"));
  return (minutes >= 570 && minutes <= 690) || (minutes >= 780 && minutes <= 900);
}

function DetailHeader({ liveQuote, quoteError, code, fallbackName, onBack, onWatch, watched }: { liveQuote: Quote | null; quoteError: boolean; code: string; fallbackName: string; onBack: () => void; onWatch: () => void; watched: boolean }) {
  const context = liveQuote ? `${liveQuote.name}（${code}）\n现价 ${liveQuote.price}，当前涨幅 ${pct(liveQuote.change_pct)}\n开 ${liveQuote.open}，高 ${liveQuote.high}，低 ${liveQuote.low}，昨收 ${liveQuote.last_close}\n成交量 ${volume(liveQuote.volume)}，成交额 ${money(liveQuote.amount_wan * 10_000)}，换手率 ${liveQuote.turnover_pct}%` : `${code} 实时行情暂不可用`;
  const metrics = liveQuote ? [
    ["开盘", liveQuote.open], ["最高", liveQuote.high], ["最低", liveQuote.low], ["昨收", liveQuote.last_close],
    ["成交量", volume(liveQuote.volume)], ["成交额", money(liveQuote.amount_wan * 10_000)], ["换手率", `${liveQuote.turnover_pct}%`],
  ] : [];
  return <GlassCard glow className="mb-4">
    <div className="mb-4 grid grid-cols-[auto_1fr_auto] items-start gap-2 sm:items-center">
      <button onClick={onBack} className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" /><span className="hidden sm:inline">返回</span></button>
      <div className="min-w-0 text-center">
        <h1 className="truncate text-xl font-bold">{liveQuote?.name || fallbackName || code}</h1>
        <p className="font-mono text-xs text-muted-foreground">{code} · A股</p>
        {liveQuote ? <p className={cn("mt-1 font-mono text-lg font-bold", color(liveQuote.change_pct))}>{liveQuote.price.toFixed(2)} <span className="ml-1 text-base">{pct(liveQuote.change_pct)}</span></p> : quoteError ? <p className="mt-1 text-xs text-warning">实时行情暂不可用</p> : <p className="mt-1 text-xs text-muted-foreground">实时行情加载中…</p>}
      </div>
      <div className="flex items-center gap-1.5"><button onClick={onWatch} aria-label={watched ? "取消自选" : "加入自选"} className={cn("inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs", watched ? "border-primary/50 bg-primary/10 text-primary" : "border-border/60 text-muted-foreground hover:text-primary")}><Star className={cn("h-3.5 w-3.5", watched && "fill-current")} /><span className="hidden lg:inline">{watched ? "已自选" : "加入自选"}</span></button><AskAiButton context={context} scopeKey={code} label="让 AI 读这只" suggestions={["基本面和估值怎么看", "近期有哪些风险", "帮我梳理验证清单"]} /></div>
    </div>
    {metrics.length > 0 && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">{metrics.map(([label, value]) => <div key={label} className="min-w-0 rounded-lg bg-muted/30 p-3"><p className="truncate text-xs text-muted-foreground">{label}</p><p className="mt-0.5 truncate font-mono text-sm font-bold">{value}</p></div>)}</div>}
  </GlassCard>;
}

export function StockDetail() {
  const { code: routeCode = "" } = useParams();
  const code = routeCode.replace(/[^\d]/g, "").slice(0, 6);
  const navigate = useNavigate();
  const [chartName, setChartName] = useState("");
  const [liveQuote, setLiveQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState(false);
  const quoteRequestIdRef = useRef(0);
  const [watch, setWatch] = useState(() => loadWatch().includes(code));
  useEffect(() => { setWatch(loadWatch().includes(code)); }, [code]);
  useEffect(() => {
    setLiveQuote(null);
    setQuoteError(false);
    const refresh = () => {
      const requestId = ++quoteRequestIdRef.current;
      api.quote(code)
        .then((rows) => { if (requestId === quoteRequestIdRef.current) { setLiveQuote(rows[code] || null); setQuoteError(!rows[code]); } })
        .catch(() => { if (requestId === quoteRequestIdRef.current) { setLiveQuote(null); setQuoteError(true); } });
    };
    refresh();
    const poll = window.setInterval(() => {
      if (document.visibilityState === "visible" && isTradingTime()) refresh();
    }, 15_000);
    const onVisibility = () => { if (document.visibilityState === "visible" && isTradingTime()) refresh(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { window.clearInterval(poll); document.removeEventListener("visibilitychange", onVisibility); quoteRequestIdRef.current += 1; };
  }, [code]);
  const toggleWatch = () => {
    const current = loadWatch();
    if (current.includes(code)) { const next = current.filter((item) => item !== code); saveWatch(next); setWatch(false); }
    else { const next = addCodes(current, code).next; saveWatch(next); setWatch(true); }
  };
  const back = () => navigate(-1);
  return <div className="min-w-0">
    <DetailHeader liveQuote={liveQuote} quoteError={quoteError} fallbackName={chartName} code={code} onBack={back} onWatch={toggleWatch} watched={watch} />
    <h2 className="sr-only">{chartName || code}行情图表</h2>
    <MarketChart asset="stock" code={code} onData={(data) => setChartName(data?.name || "")} />
    <StockResearchTabs key={code} code={code} stockName={liveQuote?.name || chartName || code} />
  </div>;
}
