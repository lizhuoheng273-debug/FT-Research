import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDownUp, BarChart3, Flame, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { MarketReviewModal } from "@/components/market/MarketReviewModal";
import { api, type MarketReview, type SectorFlow, type ShortTermEmotion, type TurnoverStock } from "@/lib/api";
import { cn } from "@/lib/utils";

const pctColor = (value: number | null) => value == null ? "text-muted-foreground" : value > 0 ? "text-danger" : value < 0 ? "text-success" : "text-muted-foreground";
const fmt = (value: number | null) => value == null ? "—" : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
const amount = (value: number | null) => value == null ? "—" : `${(value / 1e8).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 亿`;

function statusText(review: MarketReview | null) {
  if (!review) return "加载中…";
  if (review.stale) return "部分数据来自最近一次真实缓存";
  if (review.partial) return "部分市场数据暂缺";
  return review.final ? "收盘快照" : "盘中快照";
}

function EmotionDetails({ emotion }: { emotion: ShortTermEmotion }) {
  const rates: Array<[string, number | null]> = [["封板率", emotion.seal_rate], ["炸板率", emotion.break_rate], ["晋级率", emotion.promotion_rate]];
  return <div className="space-y-5">
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">{[["最高连板", `${emotion.max_boards ?? "—"} 板`], ["连板家数", `${emotion.lianban_count ?? "—"} 家`], ["涨停", `${emotion.zt_count ?? "—"} 家`], ["跌停", `${emotion.dt_count ?? "—"} 家`], ["昨涨停", `${emotion.yzt_count ?? "—"} 家`]].map(([label, value]) => <div key={label} className="rounded-lg bg-muted/30 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-mono text-lg font-bold">{value}</p></div>)}</div>
    <div className="grid grid-cols-3 gap-2">{rates.map(([label, value]) => <div key={label} className="rounded-lg bg-muted/20 p-3 text-center"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-mono font-bold">{value == null ? "—" : `${(value * 100).toFixed(1)}%`}</p></div>)}</div>
    <div><h3 className="mb-2 text-sm font-semibold">连板梯队</h3><div className="flex flex-wrap gap-2">{(emotion.ladder || []).map((tier) => <span key={tier.boards} className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">{tier.boards}{tier.plus ? "+" : ""} 板 · {tier.count} 家</span>)}</div></div>
    <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-border/50 text-left text-xs text-muted-foreground"><th className="px-2 py-2">名称</th><th className="px-2 py-2">连板</th><th className="px-2 py-2">现价</th><th className="px-2 py-2">涨跌</th><th className="px-2 py-2">成交额</th></tr></thead><tbody>{(emotion.lianban_stocks || []).map((stock) => <tr key={stock.code} className="border-b border-border/30"><td className="px-2 py-2"><Link className="font-medium hover:text-primary" to={`/finance/stocks/${stock.code}`}>{stock.name}</Link><span className="ml-1 text-xs text-muted-foreground">{stock.code}</span></td><td className="px-2 py-2 font-mono">{stock.boards} 板</td><td className="px-2 py-2 font-mono">{fmt(stock.price)}</td><td className="px-2 py-2 font-mono text-danger">+{fmt(stock.pct)}%</td><td className="px-2 py-2 font-mono">{amount(stock.amount)}</td></tr>)}</tbody></table></div>
  </div>;
}

function TurnoverRows({ rows }: { rows: TurnoverStock[] }) {
  return <div className="grid gap-2 sm:grid-cols-2">{rows.map((stock, index) => <Link key={stock.code} to={`/finance/stocks/${stock.code}`} className="flex items-center gap-2 rounded-lg bg-muted/25 px-3 py-2 transition-colors hover:bg-muted/50"><span className="w-5 font-mono text-xs text-muted-foreground/60">{index + 1}</span><span className="min-w-0 flex-1 truncate font-medium">{stock.name}</span><span className="font-mono text-sm">{fmt(stock.price)}</span><span className={cn("font-mono text-xs", pctColor(stock.pct))}>{stock.pct == null ? "—" : `${stock.pct > 0 ? "+" : ""}${stock.pct}%`}</span></Link>)}</div>;
}

function SectorTable({ sectors }: { sectors: SectorFlow[] }) {
  return <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-border/50 text-left text-xs text-muted-foreground"><th className="px-2 py-2">行业</th><th className="px-2 py-2">涨跌%</th><th className="px-2 py-2">今日净流入</th><th className="px-2 py-2">流入</th><th className="px-2 py-2">流出</th><th className="px-2 py-2">家数</th></tr></thead><tbody>{sectors.slice(0, 15).map((sector) => <tr key={sector.name} className="border-b border-border/30"><td className="px-2 py-2 font-medium">{sector.name}</td><td className={cn("px-2 py-2 font-mono", pctColor(sector.pct))}>{sector.pct > 0 ? "+" : ""}{fmt(sector.pct)}%</td><td className={cn("px-2 py-2 font-mono", pctColor(sector.net))}>{sector.net > 0 ? "+" : ""}{fmt(sector.net)} 亿</td><td className="px-2 py-2 font-mono text-muted-foreground">{fmt(sector.inflow)}</td><td className="px-2 py-2 font-mono text-muted-foreground">{fmt(sector.outflow)}</td><td className="px-2 py-2 font-mono text-muted-foreground">{sector.firms}</td></tr>)}</tbody></table></div>;
}

export function DailyReview() {
  const [review, setReview] = useState<MarketReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<"emotion" | "turnover" | null>(null);
  const load = () => { setLoading(true); setError(null); api.marketReview().then(setReview).catch((reason) => setError(reason instanceof Error ? reason.message : "市场复盘暂不可用")).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);

  const emotion = review?.shortTermEmotion;
  const turnover = review?.turnoverTop || [];
  const sectors = review?.sectors || [];
  const breadth = review?.breadth;
  const marketContext = useMemo(() => review ? [`交易日：${review.tradingDate}`, `指数：${review.indices.map((item) => `${item.name} ${item.price}（${item.changePct == null ? "涨跌缺失" : `${item.changePct > 0 ? "+" : ""}${item.changePct}%`}）`).join("；") || "数据缺口"}`, `宽度：上涨 ${review.breadth.up ?? "缺失"} 家、下跌 ${review.breadth.down ?? "缺失"} 家、涨停 ${review.breadth.limitUp ?? "缺失"}、跌停 ${review.breadth.limitDown ?? "缺失"}`, `沪深成交额：${amount(review.liquidity.todayAmountYuan)}，较上一交易日 ${amount(review.liquidity.changeAmountYuan)}（${review.liquidity.changePct == null ? "缺失" : `${review.liquidity.changePct}%`}）`, `短线情绪：${emotion ? `最高 ${emotion.max_boards} 板、连板 ${emotion.lianban_count} 家` : "数据缺口"}`, `板块资金：${sectors.slice(0, 8).map((sector) => `${sector.name} ${sector.net}`).join("；") || "数据缺口"}`].join("\n") : "市场复盘快照加载中；数据缺口：尚未返回快照", [review, emotion, sectors]);
  const upWidth = breadth?.upRatio ?? 50;
  const downWidth = breadth?.downRatio ?? 50;
  const rotation = [{ title: "流入 Top", icon: TrendingUp, color: "text-danger", rows: sectors.slice(0, 6) }, { title: "流出 Top", icon: TrendingDown, color: "text-success", rows: [...sectors].slice(-6).reverse() }];

  return <div>
    <PageHeader title="每日复盘" subtitle={`${review?.tradingDate || "—"} · ${statusText(review)}`} actions={<AskAiButton context={marketContext} analysisScope="market" workspaceSource="review" workspaceDate={review?.tradingDate} label="问 AI" suggestions={["今天大盘怎么走", "指数表现有什么分化", "盘面有什么值得验证"]} />} />
    <GlassCard glow className="mb-6"><div className="flex items-center gap-2"><span className="text-primary">✦</span><h2 className="text-sm font-semibold">AI 收盘简述</h2><span className="ml-auto text-xs text-muted-foreground">{review?.brief?.generatedAt ? new Date(review.brief.generatedAt).toLocaleString("zh-CN") : statusText(review)}</span></div>{review?.brief?.text ? <div className="prose prose-sm mt-3 max-w-none dark:prose-invert"><ReactMarkdown remarkPlugins={[remarkGfm]}>{review.brief.text}</ReactMarkdown></div> : <p className="mt-3 text-sm text-muted-foreground">{review?.brief?.status === "unavailable" ? "盘后简述生成失败，页面仍展示客观市场数据。" : review?.brief?.status === "missing" ? "数据不足以生成盘后简述，缺口会在下方标注。" : "盘后简述尚未生成。"}</p>}</GlassCard>

    <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold text-muted-foreground">大盘指数</h3><button onClick={load} className="text-muted-foreground hover:text-primary" title="刷新"><RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /></button></div>
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">{(review?.indices || [null, null, null, null]).map((index, position) => index ? <Link key={index.code} to={`/finance/indices/${index.code}`}><GlassCard className="h-full p-3 transition-colors hover:border-primary/40"><p className="truncate text-xs text-muted-foreground">{index.name}</p><p className={cn("mt-1 font-mono text-lg font-bold", pctColor(index.changePct))}>{fmt(index.price)}</p><p className={cn("text-xs", pctColor(index.changePct))}>{index.changePct == null ? "—" : `${index.changePct > 0 ? "+" : ""}${index.changePct}%`}</p><p className="mt-2 text-[10px] text-muted-foreground/60">{index.source} · {index.updatedAt || "更新时间缺失"}{index.stale ? " · 缓存" : ""}</p></GlassCard></Link> : <GlassCard key={position} className="p-3"><p className="text-xs text-muted-foreground">{loading ? "加载中…" : "行情缺失"}</p><p className="mt-1 font-mono text-lg text-muted-foreground/40">—</p></GlassCard>)}</div>

    <GlassCard className="mb-6"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold">市场宽度</h3><span className="text-xs text-muted-foreground">{review?.partial ? "部分数据" : "上涨/下跌家数"}</span></div><div className="mt-3 flex h-10 overflow-hidden rounded-lg text-sm font-semibold"><div className="flex items-center justify-start bg-danger/80 px-3 text-white" style={{ width: `${upWidth}%` }}>上涨 {breadth?.up ?? "—"}</div><div className="flex items-center justify-end bg-success/80 px-3 text-white" style={{ width: `${downWidth}%` }}>下跌 {breadth?.down ?? "—"}</div></div><div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>上涨占比 {breadth?.upRatio == null ? "—" : `${breadth.upRatio}%`}</span><span>下跌占比 {breadth?.downRatio == null ? "—" : `${breadth.downRatio}%`}</span></div><div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border/50 pt-3 text-sm"><span>今日沪深成交额 <b className="font-mono">{amount(review?.liquidity.todayAmountYuan ?? null)}</b></span><span className={cn("font-mono", pctColor(review?.liquidity.changePct ?? null))}>{review?.liquidity.direction === "expanded" ? "放量" : review?.liquidity.direction === "contracted" ? "缩量" : review?.liquidity.direction === "unchanged" ? "持平" : "缺失"} {amount(review?.liquidity.changeAmountYuan ?? null)}（{review?.liquidity.changePct == null ? "—" : `${review.liquidity.changePct}%`}）</span></div></GlassCard>

    <div className="mb-6 grid gap-4 lg:grid-cols-2"><button type="button" disabled={!emotion} onClick={() => emotion && setModal("emotion")} className={cn("glass w-full p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary", emotion && "cursor-pointer hover:border-primary/40")}><div className="flex items-center gap-2"><Flame className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold">涨停/跌停</h3><span className="ml-auto text-xs text-primary">点击查看完整短线情绪</span></div><p className="mt-4 text-lg font-semibold">{emotion ? `${emotion.zt_count ?? "—"} 涨停 · ${emotion.dt_count ?? "—"} 跌停 · 最高 ${emotion.max_boards ?? "—"} 板 · 连板 ${emotion.lianban_count ?? "—"} 家` : "短线情绪暂缺"}</p><p className="mt-2 text-xs text-muted-foreground">{emotion ? `封板率 ${emotion.seal_rate == null ? "—" : `${emotion.seal_rate * 100}%`} · 炸板率 ${emotion.break_rate == null ? "—" : `${emotion.break_rate * 100}%`} · 晋级率 ${emotion.promotion_rate == null ? "—" : `${emotion.promotion_rate * 100}%`}` : "短线情绪数据缺失"}</p></button><button type="button" disabled={turnover.length === 0} onClick={() => turnover.length > 0 && setModal("turnover")} className={cn("glass w-full p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary", turnover.length > 0 && "cursor-pointer hover:border-primary/40")}><div className="flex items-center gap-2"><BarChart3 className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold">成交额 Top20</h3><span className="ml-auto text-xs text-primary">点击查看完整榜单</span></div><div className="mt-3">{turnover.length ? <TurnoverRows rows={turnover.slice(0, 10)} /> : <p className="py-4 text-sm text-muted-foreground">成交额榜数据缺失</p>}</div></button></div>

    <div className="mb-3 flex items-center gap-2"><TrendingUp className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold text-muted-foreground">板块资金趋势</h3></div><GlassCard className="mb-6">{sectors.length ? <SectorTable sectors={sectors} /> : <p className="py-4 text-center text-sm text-muted-foreground">板块资金数据缺失</p>}</GlassCard>
    <div className="mb-3 flex items-center gap-2"><ArrowDownUp className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold text-muted-foreground">资金轮动</h3></div><div className="mb-2 grid gap-4 md:grid-cols-2">{rotation.map(({ title, icon: Icon, color, rows }) => <GlassCard key={title}><h4 className={cn("mb-3 flex items-center gap-1.5 text-sm font-semibold", color)}><Icon className="h-4 w-4" />{title}</h4>{rows.length ? <div className="space-y-1.5">{rows.map((sector, index) => <div key={sector.name} className="flex items-center gap-3 border-b border-border/30 pb-1.5 text-sm last:border-0"><span className="w-5 text-xs text-muted-foreground/50">{index + 1}</span><span className="flex-1 truncate">{sector.name}</span><span className={cn("font-mono text-xs", pctColor(sector.pct))}>{sector.pct > 0 ? "+" : ""}{fmt(sector.pct)}%</span><span className={cn("w-20 text-right font-mono text-xs", pctColor(sector.net))}>{sector.net > 0 ? "+" : ""}{fmt(sector.net)} 亿</span></div>)}</div> : <p className="py-4 text-sm text-muted-foreground">资金轮动数据缺失</p>}</GlassCard>)}</div>
    <Disclaimer />
    <MarketReviewModal open={modal === "emotion"} title="完整短线情绪" onClose={() => setModal(null)}>{emotion ? <EmotionDetails emotion={emotion} /> : <p>数据缺失</p>}</MarketReviewModal>
    <MarketReviewModal open={modal === "turnover"} title="成交额 Top20" onClose={() => setModal(null)}>{turnover.length ? <TurnoverRows rows={turnover.slice(0, 20)} /> : <p>数据缺失</p>}</MarketReviewModal>
    {error && <p className="mt-4 text-center text-sm text-warning">{error} · 可点击上方刷新重试</p>}
  </div>;
}
