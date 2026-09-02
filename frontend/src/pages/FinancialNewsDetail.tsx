import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { api, type FinancialNewsItem, type FinancialNewsSourceTimeline } from "@/lib/api";

type TimelineRow = {
  id?: string;
  title: string;
  source: string;
  publishedAt: string | null;
  summary?: string;
  originalUrl?: string;
};

function safeHref(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

export function FinancialNewsDetail() {
  const { eventId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fallback = (location.state as { fallback?: FinancialNewsItem } | null)?.fallback;
  const [event, setEvent] = useState<FinancialNewsItem | null>(fallback || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    api.financialNewsEvent(eventId)
      .then(setEvent)
      .catch((e) => setError(e instanceof Error ? e.message : "详情暂不可用"))
      .finally(() => setLoading(false));
  };

  useEffect(load, [eventId]);

  const context = useMemo(() => event ? JSON.stringify({
    title: event.title,
    sourceSummary: event.summary,
    aiDigest: event.aiDigest,
    urgencyReasons: event.urgencyReasons || event.scoreReasons,
    hotReasons: event.hotReasons || [],
    impactBreakdown: event.impactBreakdown,
    transmissionPath: event.transmissionPath,
    marketEvidence: event.marketEvidence,
    sources: event.relatedSources,
    stocks: event.relatedStocks,
  }) : "", [event]);

  const timeline: TimelineRow[] = event?.sourceTimeline?.length
    ? event.sourceTimeline.map((row: FinancialNewsSourceTimeline) => ({
      title: row.title || row.source,
      source: row.source,
      publishedAt: row.publishedAt,
      originalUrl: row.originalUrl,
    }))
    : (event?.reports || []).map((row) => ({
      id: row.id,
      title: row.title,
      source: row.source,
      publishedAt: row.publishedAt,
      summary: row.summary,
      originalUrl: row.originalUrl,
    }));

  return <div>
    <PageHeader
      title="金融资讯事件"
      subtitle="多来源归并 · 评分依据可追溯"
      actions={<button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm"><ArrowLeft className="h-4 w-4" />返回</button>}
    />
    {error && <p className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">详情暂不可用，当前展示列表缓存。<button onClick={load} className="ml-2 text-primary"><RefreshCw className="mr-1 inline h-3.5 w-3.5" />重试</button></p>}
    {!event && loading ? <p className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在加载事件详情…</p> : event && <article>
      <GlassCard className="mb-4">
        <div className="mb-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">{event.status || "最新"}</span>
          <span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">紧要 {event.urgencyScore}/100</span>
          <span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">热度 {event.hotScore}/100 · 本站计算</span>
          <span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">A股影响 {event.aShareImpactScore ?? 0}/100 · 本站计算</span>
          <span className="rounded-full bg-muted/60 px-2.5 py-1">{event.confidence || "low"} 置信度</span>
        </div>
        <h1 className="text-2xl font-bold leading-tight">{event.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>{event.source}</span><span>·</span><span>{event.latestAt || event.publishedAt}</span>
          {safeHref(event.originalUrl) && <a href={safeHref(event.originalUrl)} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-primary">打开原文 <ExternalLink className="h-3.5 w-3.5" /></a>}
        </div>
      </GlassCard>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <GlassCard>
            <h2 className="mb-2 font-semibold">来源摘要</h2>
            <p className="text-sm leading-7 text-muted-foreground">{event.summary || "暂无来源摘要，可打开原始来源查看完整内容。"}</p>
            {event.aiDigest && <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 p-3"><h3 className="text-xs font-semibold text-primary">AI 导读（辅助信息，请核对原文）</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">{event.aiDigest}</p></div>}
            <div className="mt-5 border-t border-border/50 pt-4"><AskAiButton context={context} workspaceSource="news-story" workspaceEventId={eventId} label="AI 摘要与追问" suggestions={["这件事为什么重要？", "按时间梳理相关报道", "涉及哪些行业和公司？"]} /></div>
          </GlassCard>

          <GlassCard>
            <h2 className="mb-3 font-semibold">A股传导路径</h2>
            <div className="space-y-2 text-sm">
              <p><span className="text-muted-foreground">催化事件：</span>{event.transmissionPath?.catalyst || event.title}</p>
              <p><span className="text-muted-foreground">行业：</span>{event.transmissionPath?.industry || event.category}</p>
              <p><span className="text-muted-foreground">A股板块：</span>{event.transmissionPath?.aShareSectors?.join("、") || "暂无已验证板块"}</p>
              <p><span className="text-muted-foreground">相关股票：</span>{event.transmissionPath?.relatedStocks?.join("、") || event.relatedStocks?.join("、") || "暂无已验证股票"}</p>
              <p><span className="text-muted-foreground">市场证据：</span>{event.transmissionPath?.marketEvidence?.filter(Boolean).join(" · ") || "暂无市场证据"}</p>
            </div>
          </GlassCard>

          <GlassCard>
            <h2 className="mb-3 font-semibold">相关报道时间线</h2>
            <div className="space-y-3">
              {timeline.map((report, index) => <div key={report.id || `${report.source}-${index}`} className="border-l border-primary/30 pl-4">
                <p className="font-medium">{report.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{report.source} · {report.publishedAt}</p>
                {report.summary && <p className="mt-1 text-sm text-muted-foreground">{report.summary}</p>}
                {safeHref(report.originalUrl) && <a href={safeHref(report.originalUrl)} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-primary">原文 <ExternalLink className="h-3 w-3" /></a>}
              </div>)}
            </div>
          </GlassCard>
        </div>

        <aside className="space-y-4">
          <GlassCard>
            <h2 className="mb-2 text-sm font-semibold">评分依据 · A股影响分拆解 · 本站计算</h2>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {event.impactBreakdown && Object.entries(event.impactBreakdown).map(([name, value]) => <div key={name} className="rounded-lg bg-muted/40 p-2"><p className="text-muted-foreground">{name}</p><p className="mt-1 font-mono text-primary">{value}</p></div>)}
            </div>
            <h2 className="mb-2 mt-5 border-t border-border/50 pt-4 text-sm font-semibold">紧要分依据</h2>
            <ul className="space-y-2 text-sm text-muted-foreground">{(event.urgencyReasons || event.scoreReasons)?.map((reason) => <li key={`urgent-${reason}`}>· {reason}</li>)}</ul>
            <h2 className="mb-2 mt-5 border-t border-border/50 pt-4 text-sm font-semibold">热度分依据</h2>
            <ul className="space-y-2 text-sm text-muted-foreground">{(event.hotReasons || []).map((reason) => <li key={`hot-${reason}`}>· {reason}</li>)}</ul>
          </GlassCard>

          <GlassCard>
            <h2 className="mb-2 text-sm font-semibold">市场证据</h2>
            <p className="text-sm text-muted-foreground">{event.marketEvidence?.status === "unavailable" ? "盘面/反查上游暂不可用，未据此推断。" : `已观测 ${event.marketEvidence?.verifiedStocks?.length || 0} 只股票、${event.marketEvidence?.verifiedSectors?.length || 0} 个板块`}</p>
          </GlassCard>

          <GlassCard>
            <h2 className="mb-2 text-sm font-semibold">影响范围</h2>
            <div className="flex flex-wrap gap-2"><span className="rounded-full bg-muted/60 px-2.5 py-1 text-xs">{event.category}</span>{event.relatedStocks?.map((code) => <span key={code} className="rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">{code}</span>)}</div>
            {event.impactTags?.length ? <div className="mt-4 border-t border-border/50 pt-3"><p className="mb-2 text-[11px] text-muted-foreground">AI 影响标签（辅助信息）</p><div className="flex flex-wrap gap-2">{event.impactTags.map((tag) => <span key={tag} className="rounded-full bg-primary/5 px-2.5 py-1 text-xs text-muted-foreground">{tag}</span>)}</div></div> : null}
          </GlassCard>

          <GlassCard>
            <h2 className="mb-2 text-sm font-semibold">原始来源</h2>
            <div className="space-y-2">{event.relatedSources?.map((source) => <p key={source} className="text-sm text-muted-foreground">{source}</p>)}</div>
          </GlassCard>
        </aside>
      </div>
    </article>}
  </div>;
}
