import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { AIHotFeed, type HotFeedItem, type HotFeedTopic } from "@/components/ai/AIHotFeed";
import { AISubscriptionFeed } from "@/components/ai/AISubscriptionFeed";
import { apiUrl, authHeaders } from "@/lib/api";
import { readRssSubscriptionState, removeRssSourcesById, type RssSource, type RssSubscriptionState } from "@/lib/rssSubscriptions";
import { createRssRefresher, type RssRefreshResult } from "@/lib/rssRefresh";
import { findStoryFallback, prefetchAiNewsStory, storyPublicId } from "@/lib/aiNewsStory";

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
  const [rssBulkRefreshing, setRssBulkRefreshing] = useState(false);
  const [refreshingIds, setRefreshingIds] = useState<string[]>([]);
  const [refreshMessages, setRefreshMessages] = useState<Record<string, string>>({});
  const activeLoad = useRef<AbortController | null>(null);
  const rssRefresher = useRef<ReturnType<typeof createRssRefresher> | null>(null);
  const mounted = useRef(true);

  const load = async (subscriptionStateOverride?: RssSubscriptionState) => {
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
        const customUrls = (subscriptionStateOverride ?? readRssSubscriptionState()).custom.map((source) => `urls=${encodeURIComponent(source.url)}`).join("&");
        const rssBody = await read(`/ai/rss/sources${customUrls ? `?${customUrls}` : ""}`);
        if (isCurrent()) {
          setRssSources((current) => mergeRssSources(current, (rssBody.sources || []) as RssSource[]));
          setRssBulkRefreshing(Boolean(rssBody.refreshing));
        }
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
      const result: RssRefreshResult = {
        source: body.source as RssSource,
        outcome: body.outcome as RssRefreshResult["outcome"],
        addedCount: Number(body.addedCount ?? 0),
      };
      if (body.retryAfter !== undefined) result.retryAfter = Number(body.retryAfter);
      return result;
    }, (result) => {
      if (!mounted.current) return;
      const message = result.outcome === "updated"
        ? `已更新，共新增 ${result.addedCount} 条`
        : result.outcome === "current" ? "已是最新内容" : "更新未完成，当前显示最近一次成功内容";
      setRssSources((current) => mergeRssSource(current, result.source));
      setRefreshMessages((current) => ({ ...current, [result.source.id]: message }));
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

  useEffect(() => {
    if (!rssBulkRefreshing) return;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const customUrls = readRssSubscriptionState().custom.map((source) => `urls=${encodeURIComponent(source.url)}`).join("&");
        const response = await fetch(apiUrl(`/ai/rss/sources${customUrls ? `?${customUrls}` : ""}`), { headers: authHeaders(), signal: controller.signal });
        const rssBody = await response.json();
        if (!response.ok) throw new Error(rssBody.detail || `HTTP ${response.status}`);
        if (!mounted.current) return;
        setRssSources((current) => mergeRssSources(current, (rssBody.sources || []) as RssSource[]));
        setRssBulkRefreshing(Boolean(rssBody.refreshing));
      } catch (error) {
        if (!controller.signal.aborted && mounted.current) setRssError(error instanceof Error ? error.message : "RSS 状态更新失败");
      }
    };
    const timer = window.setInterval(() => void poll(), 2000);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [rssBulkRefreshing]);

  const refreshAll = async () => {
    if (loading || rssLoading || rssBulkRefreshing) return;
    setRssBulkRefreshing(true);
    setRssError(null);
    try {
      const response = await fetch(apiUrl("/ai/rss/refresh-all"), { method:"POST", headers:authHeaders("POST") });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      setRssBulkRefreshing(Boolean(body.refreshing));
      await load();
    } catch (error) {
      setRssBulkRefreshing(false);
      setRssError(error instanceof Error ? error.message : "RSS 批量刷新失败");
    }
  };

  const refreshSource = async (source: RssSource) => {
    const refresher = rssRefresher.current;
    if (!refresher || refresher.isRefreshing(source.id)) return;
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
  const fallbackFor = (topic: HotFeedTopic, item?: HotFeedItem) => findStoryFallback(topic, items) || item;
  const prefetchStory = (topic: HotFeedTopic, item?: HotFeedItem) => {
    const fallback = fallbackFor(topic, item);
    void prefetchAiNewsStory(storyPublicId(topic, fallback)).catch(() => undefined);
  };
  const openStory = (topic: HotFeedTopic, item?: HotFeedItem) => {
    const fallback = fallbackFor(topic, item);
    const id = storyPublicId(topic, fallback);
    return navigate(`/ai/news/story/${id}`, {
    state: { fallback: { title: fallback?.title || topic.title, summary: fallback?.summary || topic.summary, reason: fallback?.reason || topic.reason, category: fallback?.category || topic.category, score: fallback?.score ?? topic.score, source: fallback?.source || topic.source, publishedAt: fallback?.publishedAt || topic.latestAt, links: { original: fallback?.links?.original || fallback?.originalUrl || topic.links?.original, story: topic.links?.story || fallback?.links?.story } } },
    });
  };

  return <div>
    <PageHeader title="AI 热点资讯" subtitle="先看热点榜，再阅读我订阅的科技媒体" actions={<div className="flex items-center gap-2"><AskAiButton context={context || "暂无 AI 热点资讯"} workspaceSource="ai-news" label="AI 摘要与追问" suggestions={["今天最重要的三件事是什么？", "这些热点有哪些共同趋势？"]} /><button type="button" onClick={() => void refreshAll()} disabled={loading || rssLoading || rssBulkRefreshing} aria-busy={loading || rssLoading || rssBulkRefreshing} aria-label={loading || rssLoading || rssBulkRefreshing ? "正在刷新 AI 热点资讯及全部 RSS" : "刷新 AI 热点资讯及全部 RSS"} className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-50"><RefreshCw className={`mr-1 inline h-4 w-4 ${(loading || rssLoading || rssBulkRefreshing) ? "animate-spin" : ""}`} />{loading || rssLoading || rssBulkRefreshing ? "刷新中…" : "刷新"}</button></div>} />
    {stale && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">AI HOT 暂时不可用，当前显示本地缓存。</p>}
    {error && <p className="mb-3 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
    <AIHotFeed topics={topics} items={items} loading={loading} onOpenStory={openStory} onPrefetchStory={prefetchStory} showEvents={false} />
    <AISubscriptionFeed sources={rssSources} loading={rssLoading} error={rssError} refreshingIds={refreshingIds} refreshMessages={refreshMessages} onRefreshSource={refreshSource} onSourcesChanged={(source) => setRssSources((current) => mergeRssSource(current, source))} onSubscriptionSourcesChanged={(state, change) => { const removedSourceIds = change?.removedSourceIds || []; if (removedSourceIds.length > 0) setRssSources((current) => removeRssSourcesById(current, removedSourceIds)); void load(state); }} />
    {!loading && topics.length === 0 && <p className="mt-4 text-sm text-muted-foreground">暂无热点资讯。</p>}
    {itemById.size === 0 && !loading && topics.length > 0 && <p className="mt-2 text-xs text-muted-foreground">部分事件暂未返回摘要，将在详情页补充。</p>}
  </div>;
}
