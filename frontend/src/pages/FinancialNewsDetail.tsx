import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { api, type FinancialHotRankItem, type FinancialHotRankPlacement, type FinancialNewsItem } from "@/lib/api";

type Story = FinancialHotRankItem | FinancialNewsItem;

function safeHref(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

function safePlacementHref(item: FinancialHotRankPlacement) {
  const roots: Record<string,string> = {ths:"10jqka.com.cn",eastmoney:"eastmoney.com",cls:"cls.cn",sina:"sina.com.cn"};
  try {
    const url = new URL(item.originalUrl);
    const root = roots[item.sourceId];
    return root && (url.hostname === root || url.hostname.endsWith(`.${root}`)) && /^https?:$/.test(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}

function isHotRankStory(story: Story): story is FinancialHotRankItem {
  return Array.isArray((story as FinancialHotRankItem).placements);
}

function formatTime(value?: string | null) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "时间未提供";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(value));
}

function legacyPlacements(story: FinancialNewsItem): FinancialHotRankPlacement[] {
  const rows = story.sourceTimeline?.length ? story.sourceTimeline : story.reports || [];
  if (rows.length) return rows.map((row, index) => ({
    sourceId: row.source || `source-${index}`,
    sourceName: row.source || "原始来源",
    listKind: "editorial",
    sourceRank: index + 1,
    title: row.title || story.title,
    publishedAt: row.publishedAt,
    originalUrl: row.originalUrl,
  }));
  return story.originalUrl ? [{
    sourceId: story.source || "source", sourceName: story.source || "原始来源",
    listKind: "editorial", sourceRank: 1, title: story.title,
    publishedAt: story.publishedAt, originalUrl: story.originalUrl,
  }] : [];
}

export function FinancialNewsDetail() {
  const { eventId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fallback = (location.state as { fallback?: Story } | null)?.fallback;
  const [event, setEvent] = useState<Story | null>(fallback || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    api.financialNewsEvent(eventId)
      .then(setEvent)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "详情暂不可用"))
      .finally(() => setLoading(false));
  };

  useEffect(load, [eventId]);

  const placements = useMemo(() => event ? (isHotRankStory(event) ? event.placements : legacyPlacements(event)) : [], [event]);
  const digest = event?.aiDigest?.trim();
  const digestStatus = event && isHotRankStory(event) ? event.aiDigestStatus : digest ? "ready" : "unavailable";
  const context = useMemo(() => event ? JSON.stringify({
    title: event.title,
    aiDigest: digest || null,
    reports: placements.map((item) => ({
      platform: item.sourceName, platformRank: item.sourceRank,
      title: item.title || event.title, publishedAt: item.publishedAt, url: item.originalUrl,
    })),
  }) : "", [event, digest, placements]);

  return <div>
    <PageHeader
      title="财经热点详情"
      subtitle="AI 导读与多平台原始报道"
      actions={<button type="button" onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm"><ArrowLeft className="h-4 w-4" />返回</button>}
    />
    {error && <p className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">详情更新失败，当前展示列表缓存。<button type="button" onClick={load} className="ml-2 text-primary"><RefreshCw className="mr-1 inline h-3.5 w-3.5" />重试</button></p>}
    {!event && loading ? <p className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在加载热点详情…</p> : event && <article className="mx-auto max-w-5xl space-y-4">
      <GlassCard glow>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {isHotRankStory(event) && <><span className="rounded-full bg-primary px-2.5 py-1 font-semibold text-primary-foreground">热点 #{event.rank}</span><span>{event.platformCount} 个平台共同关注</span></>}
          <span>{formatTime(event.publishedAt)}</span>
          {event.stale && <span className="text-warning">缓存数据</span>}
        </div>
        <h1 className="text-2xl font-bold leading-tight sm:text-3xl">{event.title}</h1>
      </GlassCard>

      <GlassCard>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Sparkles className="h-5 w-5 text-primary" />AI 导读</h2>
        {digestStatus === "ready" && digest
          ? <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{digest}</p>
          : digestStatus === "pending"
            ? <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />AI 导读生成中，稍后刷新即可查看。</p>
            : <p className="mt-3 text-sm text-muted-foreground">AI 导读暂不可用，请先查看下方各平台原始报道。</p>}
        <div className="mt-5 border-t border-border/50 pt-4"><AskAiButton context={context} workspaceSource="news-story" workspaceEventId={eventId} label="AI 摘要与追问" suggestions={["这件事为什么重要？", "比较各平台报道重点", "它可能影响哪些市场？"]} /></div>
      </GlassCard>

      <GlassCard>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2"><h2 className="text-lg font-semibold">各平台原始报道</h2><span className="text-xs text-muted-foreground">以原文为准 · 链接将在新窗口打开</span></div>
        {placements.length ? <div className="divide-y divide-border/50">{placements.map((item, index) => {
          const href = isHotRankStory(event) ? safePlacementHref(item) : safeHref(item.originalUrl);
          return <div key={`${item.sourceId}-${item.sourceRank}-${index}`} className="grid gap-2 py-4 sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-center">
            <div><p className="font-semibold">{item.sourceName}</p><p className="mt-1 text-xs text-muted-foreground">{item.listKind === "popularity" ? "热门榜" : "编辑精选"} #{item.sourceRank}</p></div>
            <div className="min-w-0"><p className="text-sm leading-6">{item.title || event.title}</p><p className="mt-1 text-xs text-muted-foreground">{formatTime(item.publishedAt)}</p></div>
            {href ? <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">打开原文<ExternalLink className="h-3.5 w-3.5" /></a> : <span className="text-xs text-muted-foreground">原文链接暂缺</span>}
          </div>;
        })}</div> : <p className="py-8 text-center text-sm text-muted-foreground">原文链接暂缺。</p>}
      </GlassCard>
    </article>}
  </div>;
}
