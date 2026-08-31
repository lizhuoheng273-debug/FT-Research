import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { AIHotFeed, type HotFeedItem, type HotFeedTopic } from "@/components/ai/AIHotFeed";
import { apiUrl, authHeaders } from "@/lib/api";

const storyId = (topic: HotFeedTopic, item?: HotFeedItem) => {
  const url = topic.links?.story || item?.links?.story || "";
  return url.split("/").pop() || topic.id;
};

export function AINews() {
  const navigate = useNavigate();
  const [topics, setTopics] = useState<HotFeedTopic[]>([]);
  const [items, setItems] = useState<HotFeedItem[]>([]);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const headers = authHeaders();
      const [hotResponse, itemResponse] = await Promise.all([
        fetch(apiUrl("/ai/news/hot-topics"), { headers }),
        fetch(apiUrl("/ai/news?mode=selected&window=24h&limit=50"), { headers }),
      ]);
      const read = async (response: Response) => { const body = await response.json(); if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`); return body; };
      const [hot, feed] = await Promise.all([read(hotResponse), read(itemResponse)]);
      setTopics((hot.items || []).sort((a: HotFeedTopic, b: HotFeedTopic) => a.rank - b.rank).slice(0, 10));
      setItems(feed.items || []);
      setStale(Boolean(hot.stale || feed.stale));
    } catch (e) { setError(e instanceof Error ? e.message : "AI 热点资讯加载失败"); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const itemById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const context = topics.map((topic) => `${topic.rank}. ${topic.title}（${topic.source || "未知来源"}）`).join("\n");
  const openStory = (topic: HotFeedTopic, item?: HotFeedItem) => navigate(`/ai/news/story/${storyId(topic, item)}`, {
    state: { fallback: { title: topic.title, summary: item?.summary, reason: item?.reason, category: item?.category, score: item?.score ?? topic.score, source: item?.source || topic.source, publishedAt: item?.publishedAt || topic.latestAt, links: { original: item?.links?.original || topic.links?.original } } },
  });

  return <div>
    <PageHeader title="AI 热点资讯" subtitle="先看热点榜，再深入阅读精选事件" actions={<div className="flex items-center gap-2"><AskAiButton context={context || "暂无 AI 热点资讯"} label="AI 摘要与追问" suggestions={["今天最重要的三件事是什么？", "这些热点有哪些共同趋势？"]} /><button onClick={() => void load()} className="rounded-lg border border-border px-3 py-1.5 text-sm"><RefreshCw className="mr-1 inline h-4 w-4" />刷新</button></div>} />
    {stale && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">AI HOT 暂时不可用，当前显示本地缓存。</p>}
    {error && <p className="mb-3 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
    <AIHotFeed topics={topics} items={items} loading={loading} onOpenStory={openStory} />
    {!loading && topics.length === 0 && <p className="mt-4 text-sm text-muted-foreground">暂无热点资讯。</p>}
    {itemById.size === 0 && !loading && topics.length > 0 && <p className="mt-2 text-xs text-muted-foreground">部分事件暂未返回摘要，将在详情页补充。</p>}
  </div>;
}
