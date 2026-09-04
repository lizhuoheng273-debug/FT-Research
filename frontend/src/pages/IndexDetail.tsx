import { useState } from "react";
import { ArrowLeft, Star } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { MarketChart } from "@/components/market/MarketChart";
import { type MarketChart as MarketChartData } from "@/lib/api";
import { cn } from "@/lib/utils";

const KEY = "vr-index-watchlist";
const load = (code: string) => { try { return localStorage.getItem(KEY)?.split(",").includes(code) || false; } catch { return false; } };
const save = (code: string, value: boolean) => { try { const items = localStorage.getItem(KEY)?.split(",").filter(Boolean) || []; const next = value ? [...new Set([...items, code])] : items.filter((item) => item !== code); localStorage.setItem(KEY, next.join(",")); } catch { /* local-only preference */ } };

export function IndexDetail() {
  const { code = "000001" } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<MarketChartData | null>(null);
  const [watched, setWatched] = useState(() => load(code));
  const quote = data?.quote;
  const points = data?.points || [];
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const rangeHigh = points.length ? Math.max(...points.map((point) => point.high)) : null;
  const rangeLow = points.length ? Math.min(...points.map((point) => point.low)) : null;
  const context = data ? `${data.name}（${code}）\n当前图表周期：${data.period}，样本 ${points.length} 根\n现价 ${quote?.price}，涨跌 ${quote?.changePct}%\n成交量 ${quote?.volume}，成交额 ${quote?.amount}\n图表区间：${firstPoint?.time || "缺失"} 至 ${lastPoint?.time || "缺失"}，区间高点 ${rangeHigh ?? "缺失"}，区间低点 ${rangeLow ?? "缺失"}\n如需 EMA、量比和波动摘要，请调用统一量价研究工具。` : `${code} 指数行情加载中；数据缺口：当前图表尚未返回`;
  return <div className="min-w-0">
    <GlassCard glow className="mb-4"><div className="flex flex-wrap items-center gap-3"><button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" />返回</button><div><h1 className="text-xl font-bold">{data?.name || code}</h1><span className="font-mono text-sm text-muted-foreground">{code} · A股指数</span></div><div className="ml-auto flex items-center gap-2"><button onClick={() => { const next = !watched; setWatched(next); save(code, next); }} className={cn("inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs", watched ? "border-primary/50 bg-primary/10 text-primary" : "border-border/60 text-muted-foreground hover:text-primary")}><Star className={cn("h-3.5 w-3.5", watched && "fill-current")} />{watched ? "已关注" : "关注指数"}</button><AskAiButton context={context} scopeKey={`index:${code}`} analysisScope="index" workspaceSource="index" workspaceCode={code} label="让 AI 读指数" suggestions={["这段指数走势如何", "成交量和波动有什么信息", "帮我列出需要验证的因素"]} /></div></div>{quote && <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">{[["现价", quote.price, quote.changePct > 0 ? "text-danger" : quote.changePct < 0 ? "text-success" : ""], ["涨跌", `${quote.change} (${quote.changePct}%)`, quote.changePct > 0 ? "text-danger" : quote.changePct < 0 ? "text-success" : ""], ["开盘", quote.open, ""], ["最高", quote.high, ""], ["最低", quote.low, ""], ["昨收", quote.prevClose, ""], ["成交量", quote.volume.toLocaleString(), ""], ["成交额", quote.amount.toLocaleString(), ""]].map(([label, value, cls]) => <div key={label} className="rounded-lg bg-muted/30 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className={cn("mt-0.5 truncate font-mono text-sm font-bold", cls)}>{value}</p></div>)}</div>}</GlassCard>
    <MarketChart asset="index" code={code} onData={setData} />
    <GlassCard className="mt-6"><h2 className="text-sm font-semibold">指数详情说明</h2><p className="mt-2 text-sm leading-relaxed text-muted-foreground">当前支持六个主要 A 股指数的行情图表。指数不提供个股财务、资金/筹码与公告卡片；数据来源、更新时间和缓存状态见上方图表。</p></GlassCard>
    <Disclaimer />
  </div>;
}
