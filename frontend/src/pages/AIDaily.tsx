import { useEffect, useMemo, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AIHotFeed, type HotFeedItem, type HotFeedTopic } from "@/components/ai/AIHotFeed";
import { apiUrl, authHeaders } from "@/lib/api";

type ReportKind = "daily" | "weekly" | "monthly";
interface ArchiveItem { kind: ReportKind; period: string; title?: string; hotCount?: number; headline?: string }
interface DailyReport { kind: "daily"; period: string; generatedAt?: string; windowStart?: string; windowEnd?: string; hotTopics?: HotFeedTopic[]; items?: HotFeedItem[] }
interface PeriodStory { title?: string; summary?: string; source?: string; publishedAt?: string; links?: { original?: string; aihot?: string }; storyId?: string }
interface PeriodTheme { title: string; summary?: string; stories?: PeriodStory[] }
interface PeriodReport { kind: "weekly" | "monthly"; period: string; title?: string; lead?: string; stats?: Record<string, number>; themes?: PeriodTheme[]; source?: { url?: string } }

const validKind = (value: string | null): ReportKind => value === "weekly" || value === "monthly" ? value : "daily";
const storyId = (story: PeriodStory) => story.storyId || story.links?.aihot?.split("/").pop() || "";

function dailyMonth(period: string) {
  const [year, month] = period.split("-");
  return year && month ? `${year} 年 ${Number(month)} 月` : period;
}

function dailyDay(period: string) {
  const day = period.split("-")[2];
  return day ? `${Number(day)} 日` : period;
}

function ArchiveRail({ kind, items, period, onSelect, onKindSelect }: { kind: ReportKind; items: ArchiveItem[]; period: string; onSelect: (value: string) => void; onKindSelect: (value: ReportKind) => void }) {
  const monthGroups = kind === "daily" ? items.reduce<{ label: string; items: ArchiveItem[] }[]>((groups, item) => {
    const label = dailyMonth(item.period);
    const group = groups.find((entry) => entry.label === label);
    if (group) group.items.push(item); else groups.push({ label, items: [item] });
    return groups;
  }, []) : [];
  const archiveItems = kind === "daily" ? monthGroups.flatMap((group) => [
    <div key={`month-${group.label}`} className="flex items-center justify-between px-2 pb-1 pt-4 first:pt-0"><span className="text-sm font-semibold text-foreground">{group.label}</span><span className="font-mono text-xs text-muted-foreground">{group.items.length}</span></div>,
    ...group.items.map((item) => <button key={item.period} onClick={() => onSelect(item.period)} title={item.headline || item.period} className={`flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left transition-colors ${item.period === period ? "border-primary/50 bg-primary/10 text-primary" : "border-transparent hover:border-border/70 hover:bg-muted/30"}`}><span className="w-10 shrink-0 font-mono text-xs text-muted-foreground">{dailyDay(item.period)}</span><span className="min-w-0 flex-1 truncate text-sm">{item.headline || "AI 热点快照"}</span><span className="shrink-0 font-mono text-[10px] text-muted-foreground">{item.hotCount ?? 0}</span></button>),
  ]) : items.map((item) => <button key={item.period} onClick={() => onSelect(item.period)} title={item.title || item.period} className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${item.period === period ? "border-primary/50 bg-primary/10 text-primary" : "border-transparent hover:border-border/70 hover:bg-muted/30"}`}><span className="block font-mono text-sm">{item.period}</span>{item.title && <span className="block truncate text-xs text-muted-foreground">{item.title}</span>}</button>);
  return <aside className="overflow-hidden rounded-xl border border-border/60 bg-muted/10 lg:sticky lg:top-5 lg:self-start"><div className="border-b border-border/60 p-3"><p className="mb-2 px-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">报告周期</p><div className="grid grid-cols-3 rounded-lg border border-border/60 bg-background/50 p-0.5">{(["daily", "weekly", "monthly"] as ReportKind[]).map((value) => <button key={value} onClick={() => onKindSelect(value)} className={`rounded-md px-2 py-2 text-xs font-medium transition-colors ${kind === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{value === "daily" ? "日报" : value === "weekly" ? "周报" : "月报"}</button>)}</div></div><div className="max-h-[calc(100vh-220px)] overflow-y-auto p-3"><p className="mb-3 px-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">{kind === "daily" ? "按月份归档" : kind === "weekly" ? "周报周期" : "月报周期"}</p>{items.length === 0 ? <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">暂无归档</p> : <div className="space-y-1">{archiveItems}</div>}</div></aside>;
}

function PeriodReport({ report }: { report: PeriodReport }) {
  const navigate = useNavigate();
  return <div className="space-y-4"><GlassCard glow><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">AI HOT {report.kind === "weekly" ? "WEEKLY" : "MONTHLY"}</p><h2 className="mt-1 text-xl font-bold">{report.title || (report.kind === "weekly" ? "AI 周报" : "AI 月报")}</h2><p className="mt-1 text-sm text-muted-foreground">{report.period}</p></div>{report.source?.url && <a href={report.source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">打开 AI HOT 原文报告 <ExternalLink className="h-3.5 w-3.5" /></a>}</div>{report.lead && <div className="mt-5 border-t border-border/50 pt-4"><p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">本期主线</p><p className="leading-relaxed">{report.lead}</p></div>}{report.stats && <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">{Object.entries(report.stats).map(([key, value]) => <div key={key} className="rounded-lg bg-muted/30 p-3"><p className="text-xl font-bold text-primary">{value}</p><p className="text-xs text-muted-foreground">{key}</p></div>)}</div>}</GlassCard>{(report.themes || []).map((theme) => <GlassCard key={theme.title}><p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">主题</p><h3 className="text-lg font-semibold">{theme.title}</h3>{theme.summary && <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{theme.summary}</p>}<div className="mt-4 space-y-3">{(theme.stories || []).map((story, index) => <article key={`${story.title}-${index}`} className="rounded-lg border border-border/50 p-3"><div className="flex items-start justify-between gap-3"><div><h4 className="font-medium">{story.title || "未命名事件"}</h4><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{story.summary || "暂无摘要"}</p></div>{story.links?.original && <a href={story.links.original} target="_blank" rel="noreferrer" className="shrink-0 text-xs text-primary hover:underline">原文</a>}</div><p className="mt-2 text-xs text-muted-foreground/70"><span className="sr-only">媒体：</span>{story.source || "AI HOT"}{story.publishedAt ? ` · ${story.publishedAt}` : ""}</p><button onClick={() => storyId(story) && navigate(`/ai/news/story/${storyId(story)}`, { state: { fallback: { title: story.title, summary: story.summary, source: story.source, publishedAt: story.publishedAt, links: story.links } } })} className="mt-2 text-xs text-primary hover:underline">查看事件详情</button></article>)}</div></GlassCard>)}</div>;
}

export function AIDaily() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const kind = validKind(searchParams.get("kind"));
  const requestedPeriod = searchParams.get("period") || "";
  const [archive, setArchive] = useState<ArchiveItem[]>([]);
  const [period, setPeriod] = useState(requestedPeriod);
  const [report, setReport] = useState<DailyReport | PeriodReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [stale, setStale] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  const load = async (targetKind: ReportKind, targetPeriod?: string) => {
    setLoading(true); setError(null);
    try {
      const headers = authHeaders();
      const indexResponse = await fetch(apiUrl(`/ai/reports/index?kind=${targetKind}`), { headers });
      const indexBody = await indexResponse.json();
      if (!indexResponse.ok) throw new Error(indexBody.detail || "报告索引暂不可用");
      const entries = (indexBody.items || []) as ArchiveItem[];
      setArchive(entries);
      const selected = targetPeriod || entries[0]?.period || "";
      setPeriod(selected);
      let response: Response;
      if (targetKind === "daily") response = await fetch(apiUrl(selected ? `/ai/reports/daily/${selected}` : "/ai/reports/daily/latest"), { headers });
      else response = await fetch(apiUrl(selected ? `/ai/reports/${targetKind}/${selected}` : `/ai/reports/${targetKind}/latest`), { headers });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "报告暂不可用");
      setReport((body.report || body) as DailyReport | PeriodReport);
      setStale(Boolean(body.stale));
      setFetchedAt(body.fetchedAt || body.report?.fetchedAt || body.report?.generatedAt);
      if (selected && (selected !== requestedPeriod || targetKind !== kind)) setSearchParams({ kind: targetKind, period: selected }, { replace: true });
    } catch (e) { setReport(null); setFetchedAt(undefined); setError(e instanceof Error ? e.message : "报告暂不可用"); }
    finally { setLoading(false); }
  };

  useEffect(() => { void load(kind, requestedPeriod); }, [kind, requestedPeriod]);
  const dailyReport = report?.kind === "daily" ? report : null;
  const periodReport = report?.kind !== "daily" ? report : null;
  const topics = dailyReport?.hotTopics || [];
  const items = dailyReport?.items || [];
  const itemById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const openStory = (topic: HotFeedTopic, item?: HotFeedItem) => { const id = topic.links?.story?.split("/").pop() || item?.links?.story?.split("/").pop() || topic.id; navigate(`/ai/news/story/${id}`, { state: { fallback: { title: topic.title, summary: item?.summary, reason: item?.reason, category: item?.category, score: item?.score ?? topic.score, source: item?.source || topic.source, publishedAt: item?.publishedAt || topic.latestAt, links: { original: item?.links?.original || topic.links?.original } } } }); };

  return <div><PageHeader title="AI 日报" subtitle="日报、周报、月报 · FT-Research AI 资讯档案" actions={<button onClick={() => void load(kind, period)} className="rounded-lg border border-border px-3 py-1.5 text-sm"><RefreshCw className="mr-1 inline h-4 w-4" />刷新</button>} />{stale && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">当前展示缓存内容{fetchedAt ? `，缓存时间：${new Date(fetchedAt).toLocaleString("zh-CN")}` : ""}。</p>}{error && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">{error}</p>}<div className="report-layout grid gap-5"><ArchiveRail kind={kind} items={archive} period={period} onSelect={(value) => setSearchParams({ kind, period: value })} onKindSelect={(value) => setSearchParams({ kind: value, period: "" })} /><main className="min-w-0">{loading ? <div className="space-y-3"><div className="h-32 animate-pulse rounded-xl bg-muted/40" /><div className="h-48 animate-pulse rounded-xl bg-muted/40" /></div> : kind === "daily" ? <><div className="mb-4 rounded-lg border border-border/50 bg-muted/20 p-3 text-sm text-muted-foreground">{dailyReport?.period || period || "暂无日期"} · 前一自然日 AI 热点快照{dailyReport?.hotTopics?.length ? ` · ${dailyReport.hotTopics.length} 条热点` : ""}</div><AIHotFeed topics={topics} items={items} onOpenStory={openStory} />{itemById.size === 0 && topics.length > 0 && <p className="mt-3 text-xs text-muted-foreground">部分事件摘要将在详情页补充。</p>}</> : periodReport ? <PeriodReport report={periodReport} /> : <p className="rounded-lg border border-dashed border-border p-5 text-sm text-muted-foreground">暂无{kind === "weekly" ? "周报" : "月报"}内容。</p>}</main></div></div>;
}
