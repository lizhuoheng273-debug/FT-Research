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
const rate = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(1)}%`;

function statusText(review: MarketReview | null) {
  if (!review) return "加载中…";
  if (review.refreshing) return "正在更新 · 先展示已有快照";
  if (review.stale) return "部分数据来自最近一次真实缓存";
  if (review.partial) return "部分市场数据暂缺";
  return review.final ? "收盘快照" : "盘中快照";
}

function briefPlaceholder(review: MarketReview | null) {
  if (!review) return "盘后简述加载中…";
  if (!review.final) return "当前尚未收盘，AI 收盘简述将在收盘后生成。";
  if (review.brief?.status === "unavailable") return "盘后简述生成失败，页面仍展示客观市场数据。";
  return "收盘数据已就绪，AI 简述生成中…";
}

function EmotionDetails({ emotion }: { emotion: ShortTermEmotion }) {
  const rates: Array<[string, number | null]> = [["封板率", emotion.seal_rate], ["炸板率", emotion.break_rate], ["晋级率", emotion.promotion_rate]];
  return <div className="space-y-5">
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">{[["最高连板", `${emotion.max_boards ?? "—"} 板`], ["连板家数", `${emotion.lianban_count ?? "—"} 家`], ["涨停", `${emotion.zt_count ?? "—"} 家`], ["跌停", `${emotion.dt_count ?? "—"} 家`], ["昨涨停", `${emotion.yzt_count ?? "—"} 家`]].map(([label, value]) => <div key={label} className="rounded-xl border border-border/60 bg-card p-3 shadow-sm"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-mono text-lg font-bold">{value}</p></div>)}</div>
    <div className="grid grid-cols-3 gap-2">{rates.map(([label, value]) => <div key={label} className="rounded-xl border border-border/60 bg-card p-3 text-center shadow-sm"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-mono font-bold">{rate(value)}</p></div>)}</div>
    <div><h3 className="mb-2 text-sm font-semibold">连板梯队</h3><div className="flex flex-wrap gap-2">{(emotion.ladder || []).map((tier) => <span key={tier.boards} className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">{tier.boards}{tier.plus ? "+" : ""} 板 · {tier.count} 家</span>)}</div></div>
    <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-border/50 text-left text-xs text-muted-foreground"><th className="px-2 py-2">名称</th><th className="px-2 py-2">连板</th><th className="px-2 py-2">现价</th><th className="px-2 py-2">涨跌</th><th className="px-2 py-2">成交额</th></tr></thead><tbody>{(emotion.lianban_stocks || []).map((stock) => <tr key={stock.code} className="border-b border-border/30"><td className="px-2 py-2"><Link className="font-medium hover:text-primary" to={`/finance/stocks/${stock.code}`}>{stock.name}</Link><span className="ml-1 text-xs text-muted-foreground">{stock.code}</span></td><td className="px-2 py-2 font-mono">{stock.boards} 板</td><td className="px-2 py-2 font-mono">{fmt(stock.price)}</td><td className="px-2 py-2 font-mono text-danger">+{fmt(stock.pct)}%</td><td className="px-2 py-2 font-mono">{amount(stock.amount)}</td></tr>)}</tbody></table></div>
  </div>;
}

function TurnoverRows({ rows }: { rows: TurnoverStock[] }) {
  return <div className="overflow-x-auto"><table className="w-full text-sm tabular-nums"><thead><tr className="border-b border-border/60 text-xs text-muted-foreground">{["排名", "名称", "现价（元）", "涨跌幅", "成交额（亿）"].map((label, index) => <th key={label} scope="col" className={cn("whitespace-nowrap px-2 py-2 font-normal", index < 2 ? "text-left" : "text-right")}>{label}</th>)}</tr></thead><tbody>{rows.map((stock, index) => <tr key={stock.code} className="border-b border-border/30 last:border-0"><td className="px-2 py-3 font-mono text-muted-foreground">{index + 1}</td><td className="whitespace-nowrap px-2 py-3"><Link to={`/finance/stocks/${stock.code}`} className="font-medium hover:text-primary">{stock.name}</Link></td><td className="px-2 py-3 text-right font-mono">{fmt(stock.price)}</td><td className={cn("whitespace-nowrap px-2 py-3 text-right font-mono", pctColor(stock.pct))}>{stock.pct == null ? "—" : `${stock.pct > 0 ? "+" : ""}${stock.pct.toFixed(2)}%`}</td><td className="px-2 py-3 text-right font-mono">{stock.amount == null ? "—" : fmt(stock.amount / 1e8)}</td></tr>)}</tbody></table></div>;
}

function SectorTable({ sectors }: { sectors: SectorFlow[] }) {
  return <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-border/50 text-left text-xs text-muted-foreground"><th className="px-2 py-2">行业</th><th className="px-2 py-2">涨跌%</th><th className="px-2 py-2">今日净流入</th><th className="px-2 py-2">流入</th><th className="px-2 py-2">流出</th><th className="px-2 py-2">家数</th></tr></thead><tbody>{sectors.slice(0, 15).map((sector) => <tr key={sector.name} className="border-b border-border/30"><td className="px-2 py-2 font-medium">{sector.name}</td><td className={cn("px-2 py-2 font-mono", pctColor(sector.pct))}>{sector.pct > 0 ? "+" : ""}{fmt(sector.pct)}%</td><td className={cn("px-2 py-2 font-mono", pctColor(sector.net))}>{sector.net > 0 ? "+" : ""}{fmt(sector.net)} 亿</td><td className="px-2 py-2 font-mono text-muted-foreground">{fmt(sector.inflow)}</td><td className="px-2 py-2 font-mono text-muted-foreground">{fmt(sector.outflow)}</td><td className="px-2 py-2 font-mono text-muted-foreground">{sector.firms}</td></tr>)}</tbody></table></div>;
}

export function DailyReview() {
  const [review, setReview] = useState<MarketReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<"emotion" | "turnover" | null>(null);
  const load = (refresh = false) => { setLoading(true); setError(null); (refresh ? api.marketReview(true) : api.marketReview()).then(setReview).catch((reason) => setError(reason instanceof Error ? reason.message : "市场复盘暂不可用")).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!review?.refreshing) return;
    const timer = window.setTimeout(load, 10000);
    return () => window.clearTimeout(timer);
  }, [review]);

  const emotion = review?.shortTermEmotion;
  const turnover = review?.turnoverTop || [];
  const sectors = review?.sectors || [];
  const breadth = review?.breadth;
  const marketContext = useMemo(() => review ? [`交易日：${review.tradingDate}`, `指数：${review.indices.map((item) => `${item.name} ${item.price}（${item.changePct == null ? "涨跌缺失" : `${item.changePct > 0 ? "+" : ""}${item.changePct}%`}）`).join("；") || "数据缺口"}`, `宽度：上涨 ${review.breadth.up ?? "缺失"} 家、下跌 ${review.breadth.down ?? "缺失"} 家、涨停 ${review.breadth.limitUp ?? "缺失"}、跌停 ${review.breadth.limitDown ?? "缺失"}`, `沪深成交额：${amount(review.liquidity.todayAmountYuan)}，较上一交易日同期 ${amount(review.liquidity.changeAmountYuan)}（${review.liquidity.changePct == null ? "缺失" : `${review.liquidity.changePct}%`}）`, `短线情绪：${emotion ? `最高 ${emotion.max_boards} 板、连板 ${emotion.lianban_count} 家` : "数据缺口"}`, `板块资金：${sectors.slice(0, 8).map((sector) => `${sector.name} ${sector.net}`).join("；") || "数据缺口"}`].join("\n") : "市场复盘快照加载中；数据缺口：尚未返回快照", [review, emotion, sectors]);
  const hasBreadth = breadth?.up != null && breadth?.down != null && breadth.up + breadth.down > 0;
  const upWidth = hasBreadth ? breadth.up! / (breadth.up! + breadth.down!) * 100 : 0;
  const downWidth = hasBreadth ? 100 - upWidth : 0;
  const breadthStatus = review?.sources?.find((source) => source.name === "breadth");
  const rotation = [{ title: "流入 Top", icon: TrendingUp, color: "text-danger", rows: sectors.slice(0, 6) }, { title: "流出 Top", icon: TrendingDown, color: "text-success", rows: [...sectors].slice(-6).reverse() }];

  return <div>
    <PageHeader title="每日复盘" subtitle={`${review?.tradingDate || "—"} · ${statusText(review)}`} actions={<AskAiButton context={marketContext} analysisScope="market" workspaceSource="review" workspaceDate={review?.tradingDate} label="问 AI" suggestions={["今天大盘怎么走", "指数表现有什么分化", "盘面有什么值得验证"]} />} />
    <GlassCard glow className="mb-6"><div className="flex items-center gap-2"><span className="text-primary">✦</span><h2 className="text-sm font-semibold">AI 收盘简述</h2><span className="ml-auto text-xs text-muted-foreground">{review?.brief?.generatedAt ? new Date(review.brief.generatedAt).toLocaleString("zh-CN") : statusText(review)}</span></div>{review?.brief?.text ? <div className="prose prose-sm mt-3 max-w-none dark:prose-invert"><ReactMarkdown remarkPlugins={[remarkGfm]}>{review.brief.text}</ReactMarkdown></div> : <p className="mt-3 text-sm text-muted-foreground">{briefPlaceholder(review)}</p>}</GlassCard>

    <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold text-muted-foreground">大盘指数</h3><button onClick={() => load(true)} className="text-muted-foreground hover:text-primary" title="刷新"><RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /></button></div>
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">{(review?.indices || [null, null, null, null]).map((index, position) => index ? <Link key={index.code} to={`/finance/indices/${index.code}`}><GlassCard className="h-full p-3 transition-colors hover:border-primary/40"><p className="truncate text-xs text-muted-foreground">{index.name}</p><p className={cn("mt-1 font-mono text-lg font-bold", pctColor(index.changePct))}>{fmt(index.price)}</p><p className={cn("text-xs", pctColor(index.changePct))}>{index.changePct == null ? "—" : `${index.changePct > 0 ? "+" : ""}${index.changePct}%`}</p><p className="mt-2 text-[10px] text-muted-foreground/60">{index.source} · {index.updatedAt || "更新时间缺失"}{index.stale ? " · 缓存" : ""}</p></GlassCard></Link> : <GlassCard key={position} className="p-3"><p className="text-xs text-muted-foreground">{loading ? "加载中…" : "行情缺失"}</p><p className="mt-1 font-mono text-lg text-muted-foreground/40">—</p></GlassCard>)}</div>

    <GlassCard className="mb-6">
      <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">市场宽度</h3><span className="text-xs text-muted-foreground">{breadthStatus?.status === "stale" ? "最近真实缓存" : "上涨/下跌家数"}</span></div>
      {hasBreadth ? <><div className="mt-4 flex justify-between gap-3 text-sm"><span className="text-danger">上涨 <b className="font-mono text-xl">{fmt(breadth!.up)}</b> 家</span><span className="text-success">下跌 <b className="font-mono text-xl">{fmt(breadth!.down)}</b> 家</span></div><div className="mt-2 flex h-3 overflow-hidden rounded-full" role="img" aria-label={`上涨${breadth!.up}家，下跌${breadth!.down}家`}><div className="bg-danger" style={{ width: `${upWidth}%` }} /><div className="bg-success" style={{ width: `${downWidth}%` }} /></div><div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>上涨占比 {upWidth.toFixed(1)}%</span><span>下跌占比 {downWidth.toFixed(1)}%</span></div></> : <p className="mt-4 rounded-lg bg-muted/30 p-3 text-sm text-muted-foreground">{loading ? "涨跌家数加载中…" : "涨跌家数暂不可用，等待数据源恢复；不以零值代替。"}</p>}
      {breadthStatus?.detail && <p className="mt-2 text-xs text-muted-foreground">{breadthStatus.detail}</p>}
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border/50 pt-3 text-sm"><span>今日沪深成交额 <b className="font-mono">{amount(review?.liquidity.todayAmountYuan ?? null)}</b></span><span className={cn("font-mono", pctColor(review?.liquidity.changePct ?? null))}>{review?.liquidity.direction ? <>{`较上一交易日同期${review.liquidity.direction === "expanded" ? "放量" : review.liquidity.direction === "contracted" ? "缩量" : "持平"}`} {amount(review.liquidity.changeAmountYuan == null ? null : Math.abs(review.liquidity.changeAmountYuan))}（{review.liquidity.changePct == null ? "—" : `${Math.abs(review.liquidity.changePct)}%`}）</> : "上一交易日同期对比暂缺"}</span></div>
    </GlassCard>

    <div className="mb-6 grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <button type="button" disabled={!emotion?.date} onClick={() => emotion && setModal("emotion")} className="glass flex h-full w-full flex-col p-4 text-left transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        <div className="flex flex-wrap items-center gap-2"><Flame className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold">涨停/跌停</h3><span className="ml-auto text-xs text-primary">查看完整短线情绪</span></div>
        <div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-xl bg-danger/5 p-3"><p className="text-xs text-muted-foreground">涨停家数</p><p className="mt-1 font-mono text-3xl font-bold text-danger">{emotion?.zt_count ?? "—"}</p></div><div className="rounded-xl bg-success/5 p-3"><p className="text-xs text-muted-foreground">跌停家数</p><p className="mt-1 font-mono text-3xl font-bold text-success">{emotion?.dt_count ?? "—"}</p></div></div>
        <p className="mt-4 text-sm">最高连板 <b className="font-mono">{emotion?.max_boards ?? "—"}</b> 板 · 连板 <b className="font-mono">{emotion?.lianban_count ?? "—"}</b> 家</p>
        <div className="mt-3 grid grid-cols-3 gap-2 border-t border-border/50 pt-3 text-xs text-muted-foreground">{[["封板率", emotion?.seal_rate], ["炸板率", emotion?.break_rate], ["晋级率", emotion?.promotion_rate]].map(([label, value]) => <div key={String(label)}>{label}<p className="mt-1 font-mono text-sm text-foreground">{rate(value as number | null | undefined)}</p></div>)}</div>
        <p className="mt-3 text-[11px] text-muted-foreground">东财涨跌停池 · {emotion?.date || "数据暂缺"}</p>
      </button>
      <GlassCard className="h-full min-w-0 p-4"><div className="flex flex-wrap items-center gap-2"><BarChart3 className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold">成交额 Top5</h3><button type="button" disabled={turnover.length === 0} onClick={() => setModal("turnover")} className="ml-auto rounded px-2 py-1 text-xs text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">查看完整榜单</button></div><div className="mt-3">{turnover.length ? <TurnoverRows rows={turnover.slice(0, 5)} /> : <p className="py-4 text-sm text-muted-foreground">成交额榜数据缺失</p>}</div></GlassCard>
    </div>

    <div className="mb-3 flex items-center gap-2"><TrendingUp className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold text-muted-foreground">板块资金趋势</h3></div><GlassCard className="mb-6">{sectors.length ? <SectorTable sectors={sectors} /> : <p className="py-4 text-center text-sm text-muted-foreground">板块资金数据缺失</p>}</GlassCard>
    <div className="mb-3 flex items-center gap-2"><ArrowDownUp className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold text-muted-foreground">资金轮动</h3></div><div className="mb-2 grid gap-4 md:grid-cols-2">{rotation.map(({ title, icon: Icon, color, rows }) => <GlassCard key={title}><h4 className={cn("mb-3 flex items-center gap-1.5 text-sm font-semibold", color)}><Icon className="h-4 w-4" />{title}</h4>{rows.length ? <div className="space-y-1.5">{rows.map((sector, index) => <div key={sector.name} className="flex items-center gap-3 border-b border-border/30 pb-1.5 text-sm last:border-0"><span className="w-5 text-xs text-muted-foreground/50">{index + 1}</span><span className="flex-1 truncate">{sector.name}</span><span className={cn("font-mono text-xs", pctColor(sector.pct))}>{sector.pct > 0 ? "+" : ""}{fmt(sector.pct)}%</span><span className={cn("w-20 text-right font-mono text-xs", pctColor(sector.net))}>{sector.net > 0 ? "+" : ""}{fmt(sector.net)} 亿</span></div>)}</div> : <p className="py-4 text-sm text-muted-foreground">资金轮动数据缺失</p>}</GlassCard>)}</div>
    <Disclaimer />
    <MarketReviewModal open={modal === "emotion"} title="完整短线情绪" onClose={() => setModal(null)}>{emotion ? <EmotionDetails emotion={emotion} /> : <p>数据缺失</p>}</MarketReviewModal>
    <MarketReviewModal open={modal === "turnover"} title="成交额 Top20" onClose={() => setModal(null)}>{turnover.length ? <TurnoverRows rows={turnover.slice(0, 20)} /> : <p>数据缺失</p>}</MarketReviewModal>
    {error && <p className="mt-4 text-center text-sm text-warning">{error} · 可点击上方刷新重试</p>}
  </div>;
}
