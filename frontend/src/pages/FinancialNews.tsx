import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, Loader2, RefreshCw, Sparkles, Star } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { api, type FinancialNewsFollowingItem, type FinancialNewsItem, type FinancialNewsOverview } from "@/lib/api";
import { loadWatch } from "@/lib/watchlist";

function safeHref(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

function formatTime(value?: string | null) {
  if (!value) return "日期缺失";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function SourceLink({ item }: { item: FinancialNewsItem }) {
  const href = safeHref(item.originalUrl);
  return href ? <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">原文 <ExternalLink className="h-3 w-3" /></a> : <span className="text-xs text-muted-foreground">原文链接暂缺</span>;
}

function ReportLinks({ item }: { item: FinancialNewsItem }) {
  const reports = (item.reports || []).filter((report) => safeHref(report.originalUrl));
  return reports.length ? <span className="flex flex-wrap gap-x-2 gap-y-1">{reports.map((report, index) => <a key={`${report.source}-${index}`} href={safeHref(report.originalUrl)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">{report.source} <ExternalLink className="h-3 w-3" /></a>)}</span> : <SourceLink item={item} />;
}

function GlobalHighlights({ items, globalExpanded, onToggle }: { items: FinancialNewsItem[]; globalExpanded: boolean; onToggle: () => void }) {
  const visible = items.slice(0, globalExpanded ? 20 : 10);
  return <GlassCard className="overflow-hidden p-0">
    <div className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent px-5 py-4"><p className="font-mono text-[10px] uppercase tracking-[0.22em] text-primary">Global Market / Highlights</p><div className="mt-1 flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /><h2 className="text-lg font-bold">全球要闻速览</h2><span className="ml-auto text-xs text-muted-foreground">默认 10 条 · 最多 20 条</span></div></div>
    <div className="hidden grid-cols-[5rem_minmax(0,1fr)_14rem] gap-3 border-b border-border/40 px-5 py-2 text-xs text-muted-foreground md:grid"><span>类别</span><span>事件简述与关键数字</span><span>来源/更新时间</span></div>
    <div className="divide-y divide-border/40">{visible.length === 0 ? <p className="py-12 text-center text-sm text-muted-foreground">等待后台生成全球资讯快照</p> : visible.map((item) => <article key={item.id} className="grid gap-2 px-5 py-4 md:grid-cols-[5rem_minmax(0,1fr)_14rem] md:gap-3"><div className="text-xs text-primary">{item.category || "全球"}</div><div className="min-w-0"><a href={safeHref(item.originalUrl)} target="_blank" rel="noreferrer" className="block text-sm font-semibold leading-6 hover:text-primary">{item.title}</a><p className="mt-1 text-sm leading-6 text-muted-foreground">{item.aiDigest || item.summary || "原始摘要暂缺"}</p><div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground"><span>重要性 {item.globalScore ?? "—"}/100</span><span>{item.globalScoreReasons?.slice(0, 1).join("") || "规则评分"}</span><ReportLinks item={item} /></div></div><div className="flex flex-wrap items-start gap-x-2 text-xs text-muted-foreground md:block"><span>{item.relatedSources?.join("、") || item.source || "来源缺失"}</span><span className="md:block md:mt-1">{formatTime(item.latestAt || item.publishedAt)}</span></div></article>)}</div>
    {items.length > 10 && <button type="button" onClick={onToggle} className="w-full border-t border-border/50 py-2.5 text-xs text-muted-foreground hover:text-primary">{globalExpanded ? "收起至 10 条" : "展开至 20 条"}</button>}
  </GlassCard>;
}

function FollowingRow({ item }: { item: FinancialNewsFollowingItem }) {
  const href = safeHref(item.originalUrl);
  const content = <><span className="shrink-0 rounded-full bg-primary/10 px-2 py-1 text-[11px] text-primary">{item.name} · {item.relationType}</span><span className="min-w-0 flex-1 text-sm leading-6">{item.title}<span className="mt-0.5 block text-xs text-muted-foreground">{item.summary || item.evidence}</span></span><span className="shrink-0 text-xs text-muted-foreground">{formatTime(item.publishedAt)}</span></>;
  return href ? <a href={href} target="_blank" rel="noreferrer" className="flex flex-col gap-2 py-3 hover:bg-muted/20 sm:flex-row sm:items-start sm:gap-3">{content}<ExternalLink className="hidden h-3.5 w-3.5 shrink-0 text-muted-foreground sm:block" /></a> : <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:gap-3">{content}<span className="shrink-0 text-xs text-muted-foreground">原文链接暂缺</span></div>;
}

export function FinancialNews() {
  const [overview, setOverview] = useState<FinancialNewsOverview | null>(null);
  const [following, setFollowing] = useState<FinancialNewsFollowingItem[]>([]);
  const [followingHasMore, setFollowingHasMore] = useState(false);
  const [followingPage, setFollowingPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [followingLoading, setFollowingLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [followingError, setFollowingError] = useState<string | null>(null);
  const [globalExpanded, setGlobalExpanded] = useState(false);
  const [codes, setCodes] = useState<string[]>([]);
  const requestVersion = useRef(0);
  const followingAbort = useRef<AbortController | null>(null);

  const loadOverview = () => { setLoading(true); setError(null); api.financialNewsOverview().then(setOverview).catch((reason) => setError(reason instanceof Error ? reason.message : "资讯快照暂不可用")).finally(() => setLoading(false)); };
  useEffect(() => { loadOverview(); }, []);
  useEffect(() => {
    const loadFollowing = () => {
      const nextCodes = loadWatch();
      setCodes(nextCodes);
      followingAbort.current?.abort();
      const controller = new AbortController();
      followingAbort.current = controller;
      const version = ++requestVersion.current;
      setFollowingPage(1); setFollowingError(null); setFollowingLoading(true);
      if (!nextCodes.length) { setFollowing([]); setFollowingHasMore(false); setFollowingLoading(false); return; }
      api.financialNewsFollowing(nextCodes, 1, 20, controller.signal).then((result) => { if (version !== requestVersion.current) return; setFollowing(result.items); setFollowingHasMore(result.hasMore); }).catch((reason) => { if (controller.signal.aborted || version !== requestVersion.current) return; setFollowingError(reason instanceof Error ? reason.message : "关注资讯暂不可用"); }).finally(() => { if (version === requestVersion.current) setFollowingLoading(false); });
    };
    loadFollowing();
    const onWatchlistUpdated = () => loadFollowing();
    const onStorage = (event: StorageEvent) => { if (event.key === "vr-watchlist") loadFollowing(); };
    window.addEventListener("vr-watchlist-updated", onWatchlistUpdated);
    window.addEventListener("storage", onStorage);
    return () => { window.removeEventListener("vr-watchlist-updated", onWatchlistUpdated); window.removeEventListener("storage", onStorage); followingAbort.current?.abort(); };
  }, []);

  const globalItems = overview?.globalHighlights || overview?.feed || [];
  const aiContext = useMemo(() => JSON.stringify({ source: "金融市场资讯", globalHighlights: globalItems.slice(0, 20).map((item) => ({ title: item.title, digest: item.aiDigest || item.summary, source: item.relatedSources || [item.source], updatedAt: item.latestAt || item.publishedAt })), following: following.map((item) => ({ code: item.code, title: item.title, relationType: item.relationType, publishedAt: item.publishedAt, evidence: item.evidence })) }, null, 2), [globalItems, following]);
  const loadMoreFollowing = () => { if (!followingHasMore || followingLoading) return; const nextPage = followingPage + 1; const controller = new AbortController(); followingAbort.current?.abort(); followingAbort.current = controller; const version = ++requestVersion.current; setFollowingLoading(true); api.financialNewsFollowing(codes, nextPage, 20, controller.signal).then((result) => { if (version !== requestVersion.current) return; setFollowing((current) => [...current, ...result.items]); setFollowingPage(nextPage); setFollowingHasMore(result.hasMore); }).catch((reason) => { if (!controller.signal.aborted && version === requestVersion.current) setFollowingError(reason instanceof Error ? reason.message : "加载更多失败"); }).finally(() => { if (version === requestVersion.current) setFollowingLoading(false); }); };

  return <div>
    <PageHeader title="金融市场资讯" subtitle="全球重要事件与我关注的股票、行业和强关联概念" actions={<div className="flex items-center gap-2"><AskAiButton context={aiContext} workspaceSource="news" label="问 AI" suggestions={["今天最重要的三条全球要闻是什么", "哪些关注消息需要优先核实", "区分事实、计划和市场预期"]} /><button type="button" onClick={loadOverview} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-primary disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}读取最新缓存</button></div>} />
    {overview?.stale && <p className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-warning">当前展示最近成功缓存；来源恢复后会由后台更新。</p>}
    {error && <p className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
    <section><GlobalHighlights items={globalItems} globalExpanded={globalExpanded} onToggle={() => setGlobalExpanded((value) => !value)} /></section>
    <section className="mt-5"><div className="mb-2 flex items-center gap-2"><Star className="h-4 w-4 text-primary" /><h2 className="font-semibold">我的关注</h2><span className="text-xs text-muted-foreground">仅使用浏览器自选股，不在服务端保存清单</span></div><GlassCard><div className="divide-y divide-border/40">{followingLoading && following.length === 0 ? <p className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在读取关注资讯…</p> : !codes.length ? <p className="py-10 text-center text-sm text-muted-foreground">还没有自选股。<Link to="/finance/stocks" className="ml-1 text-primary hover:underline">去添加自选股</Link></p> : following.length === 0 ? <p className="py-10 text-center text-sm text-muted-foreground">当前没有有依据的个股或行业资讯{followingError ? `：${followingError}` : ""}</p> : following.map((item) => <FollowingRow key={`${item.id}-${item.code}`} item={item} />)}</div>{followingHasMore && <button type="button" onClick={loadMoreFollowing} className="w-full border-t border-border/50 py-2.5 text-xs text-muted-foreground hover:text-primary">{followingLoading ? "加载中…" : "继续加载"}</button>}</GlassCard></section>
    <p className="mt-3 text-[11px] text-muted-foreground">全球评分由事件重要性、来源权威性、时效与独立确认组成；AI 简述仅作辅助，所有数字、日期和市场口径请核对原文。</p>
    <Disclaimer />
  </div>;
}
