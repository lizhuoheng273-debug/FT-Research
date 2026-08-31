import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Star } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { GlassCard } from "@/components/ui/GlassCard";
import { MarketChart } from "@/components/market/MarketChart";
import { StockData } from "@/pages/StockData";
import { api, type MarketChart as MarketChartData, type Quote } from "@/lib/api";
import { addCodes, loadWatch, saveWatch } from "@/lib/watchlist";
import { cn } from "@/lib/utils";

const color = (value: number) => value > 0 ? "text-danger" : value < 0 ? "text-success" : "text-muted-foreground";
const money = (value: number) => value >= 1e8 ? `${(value / 1e8).toFixed(2)} 亿` : value.toLocaleString();

function DetailHeader({ data, liveQuote, code, onBack, onWatch, watched }: { data: MarketChartData | null; liveQuote: Quote | null; code: string; onBack: () => void; onWatch: () => void; watched: boolean }) {
  const quote = data?.quote;
  const context = data ? `${liveQuote?.name || data.name}（${code}）\n现价 ${quote?.price}，涨跌 ${quote?.changePct}%\n开 ${quote?.open}，高 ${quote?.high}，低 ${quote?.low}，昨收 ${quote?.prevClose}\n成交量 ${quote?.volume}，成交额 ${quote?.amount}，换手率 ${liveQuote?.turnover_pct ?? "—"}%` : `${code} 行情数据加载中`;
  const metrics = quote ? [
    ["现价", quote.price, color(quote.changePct)], ["涨跌", `${quote.change > 0 ? "+" : ""}${quote.change} (${quote.changePct}%)`, color(quote.changePct)],
    ["开盘", quote.open, ""], ["最高", quote.high, ""], ["最低", quote.low, ""], ["昨收", quote.prevClose, ""],
    ["成交量", quote.volume.toLocaleString(), ""], ["成交额", money(quote.amount), ""], ["换手率", liveQuote?.turnover_pct == null ? "—" : `${liveQuote.turnover_pct}%`, ""],
  ] : [];
  return <GlassCard glow className="mb-4">
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <button onClick={onBack} className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" />返回</button>
      <div className="min-w-0"><h1 className="truncate text-xl font-bold">{liveQuote?.name || data?.name || code}</h1><span className="font-mono text-sm text-muted-foreground">{code} · A股</span></div>
      <div className="ml-auto flex items-center gap-2"><button onClick={onWatch} className={cn("inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs", watched ? "border-primary/50 bg-primary/10 text-primary" : "border-border/60 text-muted-foreground hover:text-primary")}><Star className={cn("h-3.5 w-3.5", watched && "fill-current")} />{watched ? "已自选" : "加入自选"}</button><AskAiButton context={context} scopeKey={code} label="让 AI 读这只" suggestions={["基本面和估值怎么看", "近期有哪些风险", "帮我梳理验证清单"]} /></div>
    </div>
    {metrics.length > 0 && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">{metrics.map(([label, value, cls]) => <div key={label} className="min-w-0 rounded-lg bg-muted/30 p-3"><p className="truncate text-xs text-muted-foreground">{label}</p><p className={cn("mt-0.5 truncate font-mono text-sm font-bold", cls)}>{value}</p></div>)}</div>}
  </GlassCard>;
}

export function StockDetail() {
  const { code: routeCode = "" } = useParams();
  const code = routeCode.replace(/[^\d]/g, "").slice(0, 6);
  const navigate = useNavigate();
  const [chart, setChart] = useState<MarketChartData | null>(null);
  const [liveQuote, setLiveQuote] = useState<Quote | null>(null);
  const quoteRequestIdRef = useRef(0);
  const [watch, setWatch] = useState(() => loadWatch().includes(code));
  useEffect(() => { setWatch(loadWatch().includes(code)); }, [code]);
  useEffect(() => {
    const requestId = ++quoteRequestIdRef.current;
    setLiveQuote(null);
    api.quote(code)
      .then((rows) => { if (requestId === quoteRequestIdRef.current) setLiveQuote(rows[code] || null); })
      .catch(() => { if (requestId === quoteRequestIdRef.current) setLiveQuote(null); });
    return () => { if (requestId === quoteRequestIdRef.current) quoteRequestIdRef.current += 1; };
  }, [code]);
  const toggleWatch = () => {
    const current = loadWatch();
    if (current.includes(code)) { const next = current.filter((item) => item !== code); saveWatch(next); setWatch(false); }
    else { const next = addCodes(current, code).next; saveWatch(next); setWatch(true); }
  };
  const back = () => navigate(-1);
  const title = useMemo(() => chart?.name || code, [chart, code]);
  return <div className="min-w-0">
    <DetailHeader data={chart} liveQuote={liveQuote} code={code} onBack={back} onWatch={toggleWatch} watched={watch} />
    <h2 className="sr-only">{title}行情图表</h2>
    <MarketChart asset="stock" code={code} onData={setChart} />
    <div className="mt-6 border-t border-border/60 pt-5"><StockData initialCode={code} embedded /></div>
  </div>;
}
