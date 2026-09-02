import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { AIHotFeed, type HotFeedItem, type HotFeedTopic } from "@/components/ai/AIHotFeed";
import { AISubscriptionFeed } from "@/components/ai/AISubscriptionFeed";
import { apiUrl, authHeaders } from "@/lib/api";
import { readRssSubscriptionState, type RssSource } from "@/lib/rssSubscriptions";
import { createRssRefresher } from "@/lib/rssRefresh";

const storyId = (topic: HotFeedTopic, item?: HotFeedItem) => {
  const url = topic.links?.story || item?.links?.story || "";
  return url.split("/").pop() || topic.id;
};

const attemptAt = (source: RssSource) => source.lastAttemptAt || source.lastSuccessAt || "";
const mergeRssSource = (current: RssSource[], incoming: RssSource) => [
  ...current.filter((item) => item.id !== incoming.id),
  ...(current.some((item) => item.id === incoming.id && attemptAt(item) > attemptAt(incoming)) ? current.filter((item) => item.id === incoming.id) : [incoming]),
];

const mergeRssSources = (current: RssSource[], incoming: RssSource[]) => incoming.map((source) => {
  const existing = current.find((item) => item.id === source.id);
  return existing && attemptAt(existing) > attemptAt(source) ? existing : source;
});

export function AINews() {
  const navigate = useNavigate();
  const [topics, setTopics] = useState<HotFeedTopic[]>([]);
  const [items, setItems] = useState<HotFeedItem[]>([]);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rssSources, setRssSources] = useState<RssSource[]>([]);
  const [rssLoading, setRssLoading] = useState(true);
  const [rssError, setRssError] = useState<string | null>(null);
  const [refreshingIds, setRefreshingIds] = useState<string[]>([]);
  const [refreshMessages, setRefreshMessages] = useState<Record<string, string>>({});
  const activeLoad = useRef<AbortController | null>(null);
  const rssRefresher = useRef<ReturnType<typeof createRssRefresher> | null>(null);
  const refreshOutcomes = useRef(new Map<string, "updated" | "cached">());
  const refreshKnownItems = useRef(new Map<string, Set<string>>());
  const mounted = useRef(true);

  const load = async () => {
    activeLoad.current?.abort();
    const controller = new AbortController();
    activeLoad.current = controller;
    const isCurrent = () => activeLoad.current === controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    controller.signal.addEventListener("abort", () => clearTimeout(timeout), { once: true });
    const headers = authHeaders();
    const read = async (path: string) => {
      const response = await fetch(apiUrl(path), { headers, signal: controller.signal });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      return body;
    };
    const message = (error: unknown, fallback: string) => controller.signal.aborted
      ? "请求超时，请刷新重试。" : error instanceof Error ? error.message : fallback;
    setLoading(true); setError(null);
    setRssLoading(true); setRssError(null);
    const loadHot = async () => {
      try {
        const [hot, feed] = await Promise.all([
          read("/ai/news/hot-topics"),
          read("/ai/news?mode=selected&window=24h&limit=50"),
        ]);
        if (!isCurrent()) return;
        setTopics((hot.items || []).sort((a: HotFeedTopic, b: HotFeedTopic) => a.rank - b.rank).slice(0, 10));
        setItems(feed.items || []);
        setStale(Boolean(hot.stale || feed.stale));
      } catch (e) { if (isCurrent()) setError(message(e, "AI 热点资讯加载失败")); }
      finally { if (isCurrent()) setLoading(false); }
    };
    const loadRss = async () => {
      try {
        const customUrls = readRssSubscriptionState().custom.map((source) => `urls=${encodeURIComponent(source.url)}`).join("&");
        const rssBody = await read(`/ai/rss/sources${customUrls ? `?${customUrls}` : ""}`);
        if (isCurrent()) setRssSources((current) => mergeRssSources(current, (rssBody.sources || []) as RssSource[]));
      } catch (e) { if (isCurrent()) setRssError(message(e, "媒体订阅暂不可用")); }
      finally { if (isCurrent()) setRssLoading(false); }
    };
    try { await Promise.allSettled([loadHot(), loadRss()]); }
    finally { clearTimeout(timeout); }
  };
  useEffect(() => {
    mounted.current = true;
    rssRefresher.current = createRssRefresher(async (source, signal) => {
      const custom = readRssSubscriptionState().custom.find((item) => item.id === source.id);
      const response = await fetch(apiUrl("/ai/rss/refresh"), {
        method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, signal,
        body: JSON.stringify(custom ? { sourceId: source.id, url: custom.url } : { sourceId: source.id }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      refreshOutcomes.current.set(source.id, body.outcome as "updated" | "cached");
      return body.source as RssSource;
    }, (source) => {
      if (!mounted.current) return;
      const outcome = refreshOutcomes.current.get(source.id);
      const knownItems = refreshKnownItems.current.get(source.id) || new Set<string>();
      const hasNewItems = source.items.some((item) => !knownItems.has(item.id));
      setRssSources((current) => mergeRssSource(current, source));
      setRefreshMessages((current) => ({ ...current, [source.id]: outcome === "cached"
        ? (source.items.length ? "更新失败 · 使用缓存" : "更新失败，暂无缓存内容")
        : (hasNewItems ? "已更新" : "已检查，暂无新内容") }));
    });
    void load();
    return () => {
      mounted.current = false;
      rssRefresher.current?.dispose();
      rssRefresher.current = null;
      const controller = activeLoad.current;
      activeLoad.current = null;
      controller?.abort();
    };
  }, []);

  const refreshSource = async (source: RssSource) => {
    const refresher = rssRefresher.current;
    if (!refresher || refresher.isRefreshing(source.id)) return;
    refreshKnownItems.current.set(source.id, new Set(source.items.map((item) => item.id)));
    setRefreshingIds((current) => [...current, source.id]);
    setRefreshMessages((current) => ({ ...current, [source.id]: "正在检查更新…" }));
    try {
      await refresher.refresh(source);
    } catch (error) {
      if (mounted.current) setRefreshMessages((current) => ({ ...current, [source.id]: error instanceof Error && /timeout/i.test(error.message) ? "刷新超时，请稍后重试。" : "刷新失败，请稍后重试。" }));
    } finally {
      if (mounted.current) setRefreshingIds((current) => current.filter((id) => id !== source.id));
    }
  };

  const itemById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const context = topics.map((topic) => `${topic.rank}. ${topic.title}（${topic.source || "未知来源"}）`).join("\n");
  const openStory = (topic: HotFeedTopic, item?: HotFeedItem) => navigate(`/ai/news/story/${storyId(topic, item)}`, {
    state: { fallback: { title: topic.title, summary: item?.summary, reason: item?.reason, category: item?.category, score: item?.score ?? topic.score, source: item?.source || topic.source, publishedAt: item?.publishedAt || topic.latestAt, links: { original: item?.links?.original || topic.links?.original } } },
  });

  return <div>
    <PageHeader title="AI 热点资讯" subtitle="先看热点榜，再阅读我订阅的科技媒体" actions={<div className="flex items-center gap-2"><AskAiButton context={context || "暂无 AI 热点资讯"} label="AI 摘要与追问" suggestions={["今天最重要的三件事是什么？", "这些热点有哪些共同趋势？"]} /><button onClick={() => void load()} className="rounded-lg border border-border px-3 py-1.5 text-sm"><RefreshCw className="mr-1 inline h-4 w-4" />刷新</button></div>} />
    {stale && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">AI HOT 暂时不可用，当前显示本地缓存。</p>}
    {error && <p className="mb-3 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
    <AIHotFeed topics={topics} items={items} loading={loading} onOpenStory={openStory} showEvents={false} />
    <AISubscriptionFeed sources={rssSources} loading={rssLoading} error={rssError} refreshingIds={refreshingIds} refreshMessages={refreshMessages} onRefreshSource={refreshSource} onSourcesChanged={(source) => setRssSources((current) => mergeRssSource(current, source))} />
    {!loading && topics.length === 0 && <p className="mt-4 text-sm text-muted-foreground">暂无热点资讯。</p>}
    {itemById.size === 0 && !loading && topics.length > 0 && <p className="mt-2 text-xs text-muted-foreground">部分事件暂未返回摘要，将在详情页补充。</p>}
  </div>;
}
