import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Flame, Loader2, Radio, RefreshCw, ShieldAlert, Star } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { api, type FinancialNewsItem, type FinancialNewsOverview, type GlobalIndex } from "@/lib/api";
import { loadWatch } from "@/lib/watchlist";
import { cn } from "@/lib/utils";

const CATEGORIES = ["全部", "宏观政策", "产业", "公司", "海外"] as const;
interface WatchRow { code: string; name: string; title: string; when: string; url?: string; kind: "新闻" | "公告" }

function formatTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function safeHref(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

function GlobalMarketStrip({ rows, loading, error }: { rows: GlobalIndex[]; loading: boolean; error: string | null }) {
  const regions = ["美股", "港股"];
  return <section aria-label="全球市场" className="mb-5">
    <div className="mb-2 flex items-center gap-2"><Radio className="h-4 w-4 text-primary" /><h2 className="font-semibold">全球市场</h2><span className="text-xs text-muted-foreground">美股 / 港股指数</span>{error && <span className="text-xs text-warning">{error}</span>}</div>
    <div className="grid gap-3 lg:grid-cols-2">
      {regions.map((region) => {
        const regionRows = rows.filter((row) => row.region === region);
        return <GlassCard key={region} className="p-4"><div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold">{region}</h3><span className="text-xs text-muted-foreground">{loading ? "读取中…" : regionRows.some((row) => row.status === "stale") ? "缓存" : regionRows.some((row) => row.status === "fresh") ? "实时" : "数据不可用"}</span></div><div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{regionRows.map((row) => <div key={row.key} className="min-w-0 rounded-lg bg-muted/25 p-2.5"><p className="truncate text-xs text-muted-foreground">{row.name}</p>{row.price == null ? <p className="mt-1 text-sm text-warning">数据不可用</p> : <><p className={cn("mt-1 font-mono text-sm font-semibold", row.change_pct == null ? "text-muted-foreground" : row.change_pct > 0 ? "text-danger" : row.change_pct < 0 ? "text-success" : "text-muted-foreground")}>{row.price.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}</p><p className={cn("text-xs", row.change_pct == null ? "text-muted-foreground" : row.change_pct > 0 ? "text-danger" : row.change_pct < 0 ? "text-success" : "text-muted-foreground")}>{row.change_pct == null ? "涨跌缺失" : `${row.change_pct > 0 ? "+" : ""}${row.change_pct}%`}</p></>}<p className="mt-2 truncate text-[10px] text-muted-foreground/60">{row.stale ? "缓存" : row.updatedAt || "更新时间缺失"}</p></div>)}</div></GlassCard>;
      })}
    </div>
  </section>;
}

function PriorityBoard({ title, eyebrow, icon: Icon, items, totalCount = items.length, expanded, onToggle, scoreKey, reasonKey }: {
  title: string; eyebrow: string; icon: typeof Radio; items: FinancialNewsItem[]; expanded: boolean;
  totalCount?: number; onToggle: () => void; scoreKey: "urgencyScore" | "hotScore" | "aShareImpactScore"; reasonKey: "urgencyReasons" | "hotReasons" | "impactReasons";
}) {
  const visible = items;
  return <GlassCard className="overflow-hidden p-0">
    <div className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent px-5 py-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-primary">{eyebrow}</p>
      <div className="mt-1 flex items-center gap-2"><Icon className="h-4 w-4 text-primary" /><h2 className="text-lg font-bold">{title}</h2><span className="ml-auto text-xs text-muted-foreground">本站计算</span></div>
    </div>
    <div className="divide-y divide-border/40 px-4">
      {visible.length === 0 ? <p className="py-10 text-center text-sm text-muted-foreground">等待后台生成第一份资讯快照</p> : visible.map((item, index) => <Link key={item.id} to={`/finance/news/story/${item.id}`} state={{ fallback: item }} className="group flex w-full gap-3 py-3 text-left">
        <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg font-mono text-xs font-bold", index < 3 ? "bg-primary/15 text-primary" : "bg-muted/60 text-muted-foreground")}>{index + 1}</span>
        <span className="min-w-0 flex-1"><span className="line-clamp-2 text-sm font-medium leading-5 group-hover:text-primary">{item.title}</span><span className="mt-1 flex flex-wrap gap-x-2 text-[11px] text-muted-foreground"><span>{item.source}</span><span>{formatTime(item.latestAt || item.publishedAt)}</span><span>{item.confidence ? `置信度 ${item.confidence}` : ""}</span></span><span className="mt-1 block line-clamp-1 text-[11px] text-muted-foreground">{(item.impactReasons || item[reasonKey] || item.scoreReasons)?.slice(0, 2).join(" · ")}</span><span className="mt-1 block line-clamp-1 text-[11px] text-primary">{item.transmissionPath?.aShareSectors?.join("、")}{item.relatedStocks?.length ? ` · ${item.relatedStocks.join("、")}` : ""}</span><span className="sr-only">marketEvidence {item.transmissionPath?.marketEvidence?.filter(Boolean).join(" · ")}</span></span>
        <span className="shrink-0 font-mono text-sm font-semibold text-primary">{item[scoreKey] ?? "—"}</span>
      </Link>)}
    </div>
    {totalCount > 5 && <button onClick={onToggle} className="w-full border-t border-border/50 py-2.5 text-xs text-muted-foreground hover:text-primary">{expanded ? "收起至 5 条" : "展开全部 10 条"}</button>}
  </GlassCard>;
}

export function FinancialNews() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<FinancialNewsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [urgentExpanded, setUrgentExpanded] = useState(false);
  const [hotExpanded, setHotExpanded] = useState(false);
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("全部");
  const [watchRows, setWatchRows] = useState<WatchRow[]>([]);
  const [watchLoading, setWatchLoading] = useState(true);
  const [globalRows, setGlobalRows] = useState<GlobalIndex[]>([]);
  const [globalLoading, setGlobalLoading] = useState(true);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const load = () => { setLoading(true); setError(null); api.financialNewsOverview().then(setOverview).catch((e) => setError(e instanceof Error ? e.message : "加载失败")).finally(() => setLoading(false)); };
  const loadGlobal = () => { setGlobalLoading(true); setGlobalError(null); api.globalIndices().then(setGlobalRows).catch((e) => setGlobalError(e instanceof Error ? e.message : "全球市场暂不可用")).finally(() => setGlobalLoading(false)); };
  useEffect(load, []);
  useEffect(loadGlobal, []);
  useEffect(() => {
    const codes = loadWatch();
    if (!codes.length) { setWatchRows([]); setWatchLoading(false); return; }
    Promise.all(codes.map(async (code) => {
      let name = code;
      try { const quotes = await api.quote(code); name = quotes[code]?.name || code; } catch { /* code fallback */ }
      const [news, filings] = await Promise.all([api.news(code).catch(() => []), api.announcements(code).catch(() => [])]);
      return [
        ...news.slice(0, 4).map((row): WatchRow => ({ code, name, title: row.新闻标题 || "个股新闻", when: row.发布时间 || "", url: row.新闻链接, kind: "新闻" })),
        ...filings.slice(0, 4).map((row): WatchRow => ({ code, name, title: row.title, when: row.date, url: row.url, kind: "公告" })),
      ];
    })).then((groups) => setWatchRows(groups.flat().sort((a, b) => String(b.when).localeCompare(String(a.when))).slice(0, 12))).finally(() => setWatchLoading(false));
  }, []);

  const feed = useMemo(() => (overview?.feed || []).filter((item) => category === "全部" || item.category === category).slice(0, 60), [overview, category]);
  const urgentItems = (overview?.urgent || []).slice(0, urgentExpanded ? 10 : 5);
  const hotItems = (overview?.aShareHot || overview?.hot || []).slice(0, hotExpanded ? 10 : 5);
  const globalItems = (overview?.globalObservation || []).slice(0, 5);
  const openStory = (item: FinancialNewsItem) => navigate(`/finance/news/story/${item.id}`, { state: { fallback: item } });
  const staleSources = overview?.stale ? ([
    overview.staleComponents?.quick ? `快讯最后成功 ${formatTime(overview.freshness?.quick?.lastSuccessAt)}` : null,
    overview.staleComponents?.rss ? `RSS 最后成功 ${formatTime(overview.freshness?.rss?.lastSuccessAt)}` : null,
  ].filter(Boolean) as string[]) : [];
  const unavailableSources = (overview?.sourceStatus || []).filter((source) => !source.ok).map((source) => source.source);

  return <div>
    <PageHeader title="金融市场资讯" subtitle="先看紧要、再看热门，最后按自己的关注继续下钻" actions={<button onClick={() => { load(); loadGlobal(); }} disabled={loading || globalLoading} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-primary disabled:opacity-50">{loading || globalLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}读取最新缓存</button>} />
    <GlobalMarketStrip rows={globalRows} loading={globalLoading} error={globalError} />
    {overview?.stale && <p className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-warning">当前展示缓存内容{staleSources.length ? ` · ${staleSources.join(" · ")}` : ""}</p>}
    {!overview?.stale && unavailableSources.length > 0 && <p className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-warning">部分来源暂不可用，榜单已由其他来源生成：{unavailableSources.join("、")}</p>}
    {error && <p className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}

    <section className="market-pulse-grid grid gap-4 xl:grid-cols-2">
      <PriorityBoard title="紧要快讯" eyebrow="Market Pulse / Urgent" icon={ShieldAlert} items={urgentItems} totalCount={overview?.urgent.length || 0} expanded={urgentExpanded} onToggle={() => setUrgentExpanded((value) => !value)} scoreKey="urgencyScore" reasonKey="urgencyReasons" />
      <PriorityBoard title="A股热门事件榜" eyebrow="A-Share Impact / Trending" icon={Flame} items={hotItems} totalCount={(overview?.aShareHot || overview?.hot || []).length} expanded={hotExpanded} onToggle={() => setHotExpanded((value) => !value)} scoreKey="aShareImpactScore" reasonKey="hotReasons" />
    </section>

    {globalItems.length > 0 && <section className="mt-5"><div className="mb-2 flex items-center gap-2"><Radio className="h-4 w-4 text-primary" /><h2 className="font-semibold">全球观察</h2><span className="text-xs text-muted-foreground">重大海外事件；未满足 A 股主榜证据门槛</span></div><GlassCard><div className="divide-y divide-border/40">{globalItems.map((item) => <Link key={item.id} to={`/finance/news/story/${item.id}`} state={{ fallback: item }} className="flex gap-3 py-3"><span className="w-24 shrink-0 font-mono text-xs text-muted-foreground">{formatTime(item.publishedAt)}</span><span className="min-w-0 flex-1"><span className="block font-medium">{item.title}</span><span className="mt-1 block text-xs text-muted-foreground">影响分 {item.aShareImpactScore ?? 0}/100 · {item.confidence || "low"} 置信度 · {item.source}</span></span></Link>)}</div></GlassCard></section>}

    <section className="mt-5">
      <div className="mb-2 flex items-center gap-2"><Star className="h-4 w-4 text-primary" /><h2 className="font-semibold">我的关注</h2><span className="text-xs text-muted-foreground">自选股新闻与公告，不参与公共热点排名</span></div>
      <GlassCard>
        {watchLoading ? <p className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在汇总自选资讯…</p> : watchRows.length === 0 ? <p className="py-6 text-center text-sm text-muted-foreground">暂无自选资讯；在每日复盘或自选股页面添加股票后会显示在这里。</p> : <div className="grid gap-x-6 lg:grid-cols-2">{watchRows.map((row, index) => <a key={`${row.code}-${row.kind}-${index}`} href={safeHref(row.url)} target="_blank" rel="noreferrer" className="group flex gap-3 border-b border-border/40 py-2.5 text-sm"><span className="w-14 shrink-0 text-primary">{row.name}</span><span className="min-w-0 flex-1 truncate group-hover:text-primary">{row.title}</span><span className="shrink-0 text-[11px] text-muted-foreground">{row.kind}</span></a>)}</div>}
      </GlassCard>
    </section>

    <section className="mt-5">
      <div className="mb-3 flex flex-wrap items-center gap-2"><Radio className="h-4 w-4 text-primary" /><h2 className="mr-2 font-semibold">全部资讯流</h2>{CATEGORIES.map((item) => <button key={item} onClick={() => setCategory(item)} className={cn("rounded-full border px-3 py-1 text-xs", category === item ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/50")}>{item}</button>)}</div>
      <GlassCard>{loading && !overview ? <p className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在读取资讯快照…</p> : feed.length === 0 ? <p className="py-10 text-center text-sm text-muted-foreground">当前筛选下暂无资讯</p> : <div className="divide-y divide-border/40">{feed.map((item) => <div key={item.id} role="link" tabIndex={0} onClick={() => openStory(item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") openStory(item); }} className="group flex cursor-pointer gap-4 py-3 text-left"><span className="w-24 shrink-0 font-mono text-xs text-muted-foreground">{formatTime(item.publishedAt)}</span><span className="min-w-0 flex-1"><span className="font-medium group-hover:text-primary">{item.title}</span><span className="mt-1 block line-clamp-1 text-xs text-muted-foreground">{item.summary || item.scoreReasons?.join(" · ")}</span></span><span className="hidden shrink-0 text-xs text-muted-foreground sm:block">{item.category} · {item.independentSourceCount ?? item.relatedSourceCount} 独立源</span>{safeHref(item.originalUrl) && <a href={safeHref(item.originalUrl)} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="shrink-0 text-muted-foreground hover:text-primary" title="打开原文"><ExternalLink className="h-4 w-4" /></a>}</div>)}</div>}</GlassCard>
    </section>
    <p className="mt-3 text-[11px] text-muted-foreground">“紧要分”和“事件热度”为 FT-Research 基于来源、时效与独立报道数计算，不代表阅读量、评论量或投资建议。</p>
    <Disclaimer />
  </div>;
}
