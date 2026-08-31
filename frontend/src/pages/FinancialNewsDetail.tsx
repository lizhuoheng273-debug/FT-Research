import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { api, type FinancialNewsItem } from "@/lib/api";

export function FinancialNewsDetail() {
  const { eventId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fallback = (location.state as { fallback?: FinancialNewsItem } | null)?.fallback;
  const [event, setEvent] = useState<FinancialNewsItem | null>(fallback || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setLoading(true); setError(null); api.financialNewsEvent(eventId).then(setEvent).catch((e) => setError(e instanceof Error ? e.message : "详情暂不可用")).finally(() => setLoading(false)); };
  useEffect(load, [eventId]);
  const context = useMemo(() => event ? JSON.stringify({ title: event.title, digest: event.aiDigest || event.summary, reasons: event.scoreReasons, sources: event.relatedSources, stocks: event.relatedStocks }) : "", [event]);

  return <div>
    <PageHeader title="金融资讯事件" subtitle="多来源归并 · 评分依据可追溯" actions={<button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm"><ArrowLeft className="h-4 w-4" />返回</button>} />
    {error && <p className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">详情暂不可用，当前展示列表缓存。<button onClick={load} className="ml-2 text-primary"><RefreshCw className="mr-1 inline h-3.5 w-3.5" />重试</button></p>}
    {!event && loading ? <p className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在加载事件详情…</p> : event && <article>
      <GlassCard className="mb-4"><div className="mb-3 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">{event.status || "最新"}</span><span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">紧要 {event.urgencyScore}/100</span><span className="rounded-full bg-primary/15 px-2.5 py-1 text-primary">热度 {event.hotScore}/100 · 本站计算</span></div><h1 className="text-2xl font-bold leading-tight">{event.title}</h1><div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground"><span>{event.source}</span><span>·</span><span>{event.publishedAt}</span>{event.originalUrl && <a href={event.originalUrl} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-primary">打开原文 <ExternalLink className="h-3.5 w-3.5" /></a>}</div></GlassCard>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4"><GlassCard><h2 className="mb-2 font-semibold">事件导读</h2><p className="text-sm leading-7 text-muted-foreground">{event.aiDigest || event.summary || "暂无摘要，可打开原始来源查看完整内容。"}</p><div className="mt-5 border-t border-border/50 pt-4"><AskAiButton context={context} label="AI 摘要与追问" suggestions={["这件事为什么重要？", "按时间梳理相关报道", "涉及哪些行业和公司？"]} /></div></GlassCard><GlassCard><h2 className="mb-3 font-semibold">相关报道时间线</h2><div className="space-y-3">{(event.reports || []).map((report, index) => <div key={report.id || index} className="border-l border-primary/30 pl-4"><p className="font-medium">{report.title}</p><p className="mt-1 text-xs text-muted-foreground">{report.source} · {report.publishedAt}</p>{report.summary && <p className="mt-1 text-sm text-muted-foreground">{report.summary}</p>}{report.originalUrl && <a href={report.originalUrl} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-primary">原文 <ExternalLink className="h-3 w-3" /></a>}</div>)}</div></GlassCard></div>
        <aside className="space-y-4"><GlassCard><h2 className="mb-2 text-sm font-semibold">评分依据</h2><ul className="space-y-2 text-sm text-muted-foreground">{event.scoreReasons?.map((reason) => <li key={reason}>· {reason}</li>)}</ul></GlassCard><GlassCard><h2 className="mb-2 text-sm font-semibold">影响范围</h2><div className="flex flex-wrap gap-2">{(event.impactTags || [event.category]).map((tag) => <span key={tag} className="rounded-full bg-muted/60 px-2.5 py-1 text-xs">{tag}</span>)}{event.relatedStocks?.map((code) => <span key={code} className="rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">{code}</span>)}</div></GlassCard><GlassCard><h2 className="mb-2 text-sm font-semibold">原始来源</h2><div className="space-y-2">{event.relatedSources?.map((source) => <p key={source} className="text-sm text-muted-foreground">{source}</p>)}</div></GlassCard></aside>
      </div>
    </article>}
  </div>;
}
