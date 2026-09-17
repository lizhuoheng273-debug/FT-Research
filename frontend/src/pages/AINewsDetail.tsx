import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink, Heart, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { loadAiNewsStory, takePrefetchedAiNewsStory } from "@/lib/aiNewsStory";
import { storageGet, storageSet } from "@/lib/storage";

interface Report { id?: string; title?: string; summary?: string; source?: { name?: string } | string; publishedAt?: string; links?: { original?: string; aihot?: string } }
interface Fallback extends Report { reason?: string; category?: string; score?: number }
interface Story { title?: string; digest?: string; latest?: string; score?: number; tags?: string[]; category?: string; sourceCount?: number; reportCount?: number; firstReportAt?: string; latestAt?: string; links?: { aihot?: string; original?: string }; reports?: Report[]; storyline?: Array<{ publicId?: string; title?: string; relation?: string; links?: { aihot?: string } }> }
interface LoadState { storyId?: string; reloadKey: number; loading: boolean; failed: boolean }
interface StoryState { storyId: string; story: Story }

const sourceName = (source?: Report["source"]) => typeof source === "string" ? source : source?.name;

export function AINewsDetail() {
  const { storyId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fallback = (location.state as { fallback?: Fallback } | null)?.fallback;
  const [storyState, setStoryState] = useState<StoryState | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [loadState, setLoadState] = useState<LoadState>({ storyId, reloadKey: 0, loading: true, failed: false });
  const [favoriteState, setFavoriteState] = useState(() => ({ storyId, value: storageGet(`ft-story-star:${storyId}`) === "1" }));

  useEffect(() => {
    if (!storyId) {
      setLoadState({ storyId, reloadKey, loading: false, failed: true });
      return;
    }

    const controller = new AbortController();
    let active = true;
    setLoadState({ storyId, reloadKey, loading: true, failed: false });

    const prefetched = takePrefetchedAiNewsStory(storyId);
    const request = prefetched ?? loadAiNewsStory(storyId, { signal: controller.signal, retries: 2 });
    void request
      .then((loadedStory) => {
        if (active) setStoryState({ storyId, story: loadedStory as Story });
      })
      .catch((loadError: unknown) => {
        if (!active || (loadError instanceof Error && loadError.name === "AbortError")) return;
        setLoadState({ storyId, reloadKey, loading: false, failed: true });
      })
      .finally(() => {
        if (active) {
          setLoadState((current) => current.storyId === storyId && current.reloadKey === reloadKey
            ? { ...current, loading: false }
            : current);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [storyId, reloadKey]);

  const matchingLoadState = loadState.storyId === storyId && loadState.reloadKey === reloadKey;
  const loading = !matchingLoadState || loadState.loading;
  const error = matchingLoadState && !loadState.loading && loadState.failed;
  const story = storyState && storyState.storyId === storyId ? storyState.story : null;
  const favorite = favoriteState.storyId === storyId ? favoriteState.value : storageGet(`ft-story-star:${storyId}`) === "1";
  const title = story?.title || fallback?.title || "AI 热点事件";
  const digest = story?.digest || fallback?.summary || "";
  const tags = story?.tags || (story?.category || fallback?.category ? [story?.category || fallback?.category || "AI"] : ["AI"]);
  const originalLink = story?.links?.original || fallback?.links?.original || story?.reports?.find((report) => report.links?.original)?.links?.original;
  const context = useMemo(() => `${title}\n${digest}\n${story?.latest || ""}`, [title, digest, story?.latest]);
  const retry = () => setReloadKey((current) => current + 1);
  const toggleFavorite = () => {
    const next = !favorite;
    setFavoriteState({ storyId, value: next });
    if (storyId) storageSet(`ft-story-star:${storyId}`, next ? "1" : "0");
  };

  return <div>
    <PageHeader title="热点详情" subtitle="AI HOT 精选事件 · FT-Research" actions={<button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm"><ArrowLeft className="h-4 w-4" />返回</button>} />
    {error && fallback && <p role="status" className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">完整详情暂时未加载成功。<button onClick={retry} className="ml-2 text-primary hover:underline"><RefreshCw className="mr-1 inline h-3.5 w-3.5" />重新加载</button>{originalLink && <a href={originalLink} target="_blank" rel="noreferrer" className="ml-3 inline-flex items-center gap-1 text-primary hover:underline">查看原文 <ExternalLink className="h-3.5 w-3.5" /></a>}</p>}
    <article>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">精选</span><span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">AI 热点</span>{(story?.score ?? fallback?.score) != null && <span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">AI 评分 {story?.score ?? fallback?.score}/100</span>}{story?.sourceCount && <span>{story.sourceCount} 个来源</span>}<button onClick={toggleFavorite} className="ml-auto inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 hover:text-primary"><Heart className={`h-3.5 w-3.5 ${favorite ? "fill-primary text-primary" : ""}`} />{favorite ? "已收藏" : "收藏"}</button></div>
      <GlassCard className="mb-4"><h1 className="text-2xl font-bold leading-tight">{title}</h1><div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground"><span>{sourceName(story?.reports?.[0]?.source) || sourceName(fallback?.source) || "AI HOT"}</span><span>·</span><span>{story?.latestAt || fallback?.publishedAt || ""}</span>{originalLink && <a href={originalLink} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-primary hover:underline">查看原文 <ExternalLink className="h-3.5 w-3.5" /></a>}{story?.links?.aihot && <a href={story.links.aihot} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">打开 AI HOT <ExternalLink className="h-3.5 w-3.5" /></a>}</div></GlassCard>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <GlassCard><h2 className="mb-2 text-base font-semibold">AI 导读</h2>{!digest && loading ? <div aria-label="AI 导读加载中" className="space-y-2 animate-pulse"><div className="h-4 w-full rounded bg-muted/60" /><div className="h-4 w-5/6 rounded bg-muted/60" /><div className="h-4 w-2/3 rounded bg-muted/60" /></div> : digest ? <div className="prose prose-sm max-w-none dark:prose-invert"><ReactMarkdown remarkPlugins={[remarkGfm]}>{digest}</ReactMarkdown></div> : null}{story?.latest && <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm"><b>最新进展：</b>{story.latest}</div>}<div className="mt-5 border-t border-border/50 pt-4"><AskAiButton context={context} workspaceSource="ai-news" workspaceEventId={storyId} label="AI 摘要与追问" suggestions={["这件事最值得关注的影响是什么？", "帮我梳理这件事的时间线"]} /></div></GlassCard>
        <aside className="space-y-4">{fallback?.reason && <GlassCard><h2 className="mb-2 text-sm font-semibold">推荐理由</h2><p className="text-sm leading-relaxed text-muted-foreground">{fallback.reason}</p></GlassCard>}{tags.length > 0 && <GlassCard><h2 className="mb-2 text-sm font-semibold">标签</h2><div className="flex flex-wrap gap-2">{tags.map((tag) => <span key={tag} className="rounded-full bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground">#{tag}</span>)}</div></GlassCard>}<GlassCard><h2 className="mb-2 text-sm font-semibold">报道概览</h2><div className="space-y-2 text-sm text-muted-foreground"><p>报道数：{story?.reportCount ?? story?.reports?.length ?? "—"}</p><p>首次报道：{story?.firstReportAt || "—"}</p><p>最近更新：{story?.latestAt || "—"}</p></div></GlassCard></aside>
      </div>
      {error && !fallback && <div role="alert"><GlassCard className="mt-4"><p className="text-sm text-muted-foreground">完整详情暂时未加载成功。</p><div className="mt-3 flex flex-wrap items-center gap-3"><button onClick={retry} className="inline-flex items-center gap-1 text-primary hover:underline"><RefreshCw className="h-3.5 w-3.5" />重新加载</button>{originalLink && <a href={originalLink} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">查看原文 <ExternalLink className="h-3.5 w-3.5" /></a>}</div></GlassCard></div>}
      <div className="mt-4 space-y-3"><h2 className="text-lg font-semibold">报道时间线</h2>{story?.reports?.map((report, index) => <GlassCard key={report.id || index}><div className="flex items-start justify-between gap-3"><div><h3 className="font-medium">{report.title}</h3><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{report.summary || "暂无摘要"}</p><p className="mt-2 text-xs text-muted-foreground/70">{typeof report.source === "string" ? report.source : report.source?.name} · {report.publishedAt || ""}</p></div>{report.links?.original && <a href={report.links.original} target="_blank" rel="noreferrer" className="shrink-0 text-xs text-primary hover:underline">原文</a>}</div></GlassCard>)}{loading && !story?.reports?.length && <div aria-label="报道时间线加载中" className="space-y-3 animate-pulse"><div className="h-24 rounded-xl bg-muted/50" /><div className="h-24 rounded-xl bg-muted/50" /></div>}</div>
    </article>
  </div>;
}
