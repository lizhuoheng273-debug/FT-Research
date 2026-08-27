import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { authHeaders } from "@/lib/api";

interface Item { id: string; title: string; summary?: string; score?: number; reason?: string; category?: string; publishedAt?: string; source?: string; links?: { aihot?: string; original?: string; story?: string } }
interface HotTopic { rank: number; id: string; title: string; source?: string; sourceCount?: number; signalCount?: number; latestAt?: string; links?: { aihot?: string; original?: string; story?: string } }

const storyId = (topic: HotTopic, item?: Item) => {
  const url = topic.links?.story || item?.links?.story || "";
  return url.split("/").pop() || topic.id;
};

function Skeletons() {
  return <div className="space-y-3" aria-label="正在加载热点"><div className="h-32 animate-pulse rounded-xl bg-muted/40" /><div className="h-32 animate-pulse rounded-xl bg-muted/40" /><div className="h-32 animate-pulse rounded-xl bg-muted/40" /></div>;
}

export function AINews() {
  const navigate = useNavigate();
  const [topics, setTopics] = useState<HotTopic[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const headers = authHeaders();
      const [hotResponse, itemResponse] = await Promise.all([
        fetch("/api/ai/news/hot-topics", { headers }),
        fetch("/api/ai/news?mode=selected&window=24h&limit=50", { headers }),
      ]);
      const read = async (response: Response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
        return body;
      };
      const [hot, feed] = await Promise.all([read(hotResponse), read(itemResponse)]);
      setTopics((hot.items || []).sort((a: HotTopic, b: HotTopic) => a.rank - b.rank).slice(0, 10));
      setItems(feed.items || []);
      setStale(Boolean(hot.stale || feed.stale));
    } catch (e) { setError(e instanceof Error ? e.message : "AI 热点资讯加载失败"); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const itemById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const cards = topics.map((topic) => ({ topic, item: itemById.get(topic.id) }));
  const context = cards.map(({ topic, item }) => `${topic.rank}. ${topic.title}（${topic.source || item?.source || "未知来源"}）`).join("\n");
  const visibleTopics = topics.slice(0, expanded ? 10 : 5);
  const openStory = (topic: HotTopic, item?: Item) => navigate(`/ai/news/story/${storyId(topic, item)}`, {
    state: { fallback: { title: topic.title, summary: item?.summary, reason: item?.reason, category: item?.category, score: item?.score, source: item?.source || topic.source, publishedAt: item?.publishedAt || topic.latestAt, links: { original: item?.links?.original || topic.links?.original } } },
  });

  return <div>
    <PageHeader title="AI 热点资讯" subtitle="先看热点榜，再深入阅读精选事件" actions={<div className="flex items-center gap-2"><AskAiButton context={context || "暂无 AI 热点资讯"} label="AI 摘要与追问" suggestions={["今天最重要的三件事是什么？", "这些热点有哪些共同趋势？"]} /><button onClick={() => void load()} className="rounded-lg border border-border px-3 py-1.5 text-sm"><RefreshCw className="mr-1 inline h-4 w-4" />刷新</button></div>} />
    {stale && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">AI HOT 暂时不可用，当前显示本地缓存。</p>}
    {error && <p className="mb-3 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
    <GlassCard className="mb-5" glow>
      <div className="mb-3 flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">AI HOT / HOT TOPICS</p><h2 className="mt-1 text-lg font-semibold">热点榜</h2></div><span className="text-xs text-muted-foreground">{topics.length ? `Top ${topics.length}` : "加载中"}</span></div>
      {loading ? <div className="space-y-2"><div className="h-8 animate-pulse rounded bg-muted/40" /><div className="h-8 animate-pulse rounded bg-muted/40" /><div className="h-8 animate-pulse rounded bg-muted/40" /></div> : <div className="divide-y divide-border/40">{visibleTopics.map((topic) => <button key={topic.id} onClick={() => openStory(topic, itemById.get(topic.id))} className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:text-primary"><span className="w-6 shrink-0 text-center font-mono text-sm font-bold text-primary">{topic.rank}</span><span className="min-w-0 flex-1 truncate text-sm font-medium">{topic.title}</span><span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">{topic.source || "AI HOT"}</span><span className="shrink-0 text-xs text-muted-foreground">{topic.sourceCount ? `${topic.sourceCount} 源` : ""}</span></button>)}</div>}
      {!loading && topics.length > 5 && <button onClick={() => setExpanded((value) => !value)} className="mt-3 flex w-full items-center justify-center gap-1 rounded-lg border border-border/60 py-2 text-xs text-muted-foreground hover:text-primary">{expanded ? "收起至前 5 条" : "展开全部 10 条"}<ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} /></button>}
    </GlassCard>

    <div className="mb-3 flex items-baseline justify-between"><h2 className="text-lg font-semibold">精选事件</h2><span className="text-xs text-muted-foreground">共 {cards.length} 条</span></div>
    {loading ? <Skeletons /> : <div className="space-y-3">{cards.map(({ topic, item }) => <div key={topic.id} role="link" tabIndex={0} onClick={() => openStory(topic, item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") openStory(topic, item); }} className="cursor-pointer"><GlassCard className="transition-colors hover:border-primary/40"><div className="flex gap-3"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 font-mono text-sm font-bold text-primary">{topic.rank}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="font-semibold">{topic.title}</h3><span className="font-mono text-xs text-primary">{item?.score != null ? `热度 ${item.score}` : "热点"}</span></div><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{item?.summary || "点击查看事件详情与报道时间线"}</p><div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground/70"><span>{topic.source || item?.source || "AI HOT"}</span><span>{item?.publishedAt || topic.latestAt || ""}</span>{item?.reason && <span className="text-primary/80"><Sparkles className="mr-1 inline h-3 w-3" />{item.reason}</span>}{item?.links?.original && <a href={item.links.original} target="_blank" rel="noreferrer" onClick={(event) => { event.stopPropagation(); }} className="hover:text-primary"><ExternalLink className="mr-1 inline h-3 w-3" />原文</a>}{topic.links?.aihot && <a href={topic.links.aihot} target="_blank" rel="noreferrer" onClick={(event) => { event.stopPropagation(); }} className="hover:text-primary">AI HOT</a>}</div></div></div></GlassCard></div>)}</div>}
  </div>;
}
