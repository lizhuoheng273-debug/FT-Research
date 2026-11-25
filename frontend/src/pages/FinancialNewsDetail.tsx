import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ChevronRight, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  api,
  type FinancialHotRankItem,
  type FinancialNewsItem,
  type FinancialReportDetail,
} from "@/lib/api";

type LegacyStory = FinancialHotRankItem | FinancialNewsItem;

function safeHref(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

function adaptLegacy(item: LegacyStory): FinancialReportDetail {
  const isHot = Array.isArray((item as FinancialHotRankItem).placements);
  const placements = isHot ? (item as FinancialHotRankItem).placements : [];
  const legacy = item as FinancialNewsItem;
  const followups = isHot
    ? placements.slice(1).map((pl, idx) => ({
        reportKey: `${item.id}-${idx}`,
        title: pl.title || item.title,
        sourceName: pl.sourceName,
        publishedAt: pl.publishedAt || null,
        relativeTime: "同热榜",
        originalUrl: pl.originalUrl,
        role: "report",
      }))
    : (legacy.reports || []).slice(1).map((rep, idx) => ({
        reportKey: rep.id || `${item.id}-${idx}`,
        title: rep.title,
        sourceName: rep.source,
        publishedAt: rep.publishedAt,
        relativeTime: "同事件",
        originalUrl: rep.originalUrl,
        role: "report",
      }));

  return {
    reportKey: item.id,
    title: item.title,
    summary: (isHot ? item.aiDigest : legacy.summary || legacy.aiDigest) || item.title,
    publishedAt: item.publishedAt,
    timeLabel: item.publishedAt ? item.publishedAt.slice(0, 16).replace("T", " ") : "近期",
    relativeTime: "近期",
    sourceName: isHot ? placements[0]?.sourceName || "平台热榜" : legacy.source || "公开来源",
    sourceTier: isHot ? "平台热榜" : "公开报道",
    originalUrl: item.originalUrl || placements[0]?.originalUrl || "",
    bucket: "china",
    bucketName: isHot ? "财经热点" : legacy.category || "财经资讯",
    tags: isHot ? ["平台热榜"] : legacy.impactTags || [],
    eventSummary: null,
    followups,
  };
}

export function FinancialNewsDetail() {
  const { eventId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fallback = (location.state as { fallback?: LegacyStory } | null)?.fallback;
  const [detail, setDetail] = useState<FinancialReportDetail | null>(fallback ? adaptLegacy(fallback) : null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .financialNewsReportDetail(eventId)
      .then(setDetail)
      .catch(() =>
        api
          .financialNewsEvent(eventId)
          .then((legacy) => setDetail(adaptLegacy(legacy)))
          .catch((reason) => setError(reason instanceof Error ? reason.message : "资讯详情暂不可用")),
      )
      .finally(() => setLoading(false));
  };

  useEffect(load, [eventId]);

  const context = useMemo(
    () =>
      detail
        ? JSON.stringify(
            {
              title: detail.title,
              source: detail.sourceName,
              publishedAt: detail.publishedAt,
              summary: detail.summary,
              originalUrl: detail.originalUrl,
              event: detail.eventSummary,
              followups: detail.followups.slice(0, 8),
            },
            null,
            2,
          )
        : "",
    [detail],
  );

  const originalHref = safeHref(detail?.originalUrl);

  return (
    <div>
      <PageHeader
        title="金融资讯详情"
        subtitle="核验事实摘要 · 同事件后续报道"
        actions={
          <div className="flex items-center gap-2">
            {detail && (
              <AskAiButton
                context={context}
                workspaceSource="news-story"
                workspaceEventId={eventId}
                label="针对此条问 AI"
                suggestions={["这件事为什么重要？", "梳理同事件前后变化", "涉及哪些行业与传导路径？"]}
              />
            )}
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm hover:border-primary"
            >
              <ArrowLeft className="h-4 w-4" />
              返回
            </button>
          </div>
        }
      />

      {error && (
        <p className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">
          {error}
          <button type="button" onClick={load} className="ml-2 text-primary">
            <RefreshCw className="mr-1 inline h-3.5 w-3.5" />
            重试
          </button>
        </p>
      )}

      {!detail && loading ? (
        <p className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在加载资讯详情…
        </p>
      ) : detail ? (
        <article className="mx-auto max-w-4xl space-y-5">
          <GlassCard glow>
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="rounded bg-primary/15 px-2 py-0.5 font-medium text-primary">{detail.bucketName}</span>
              <span>
                {detail.sourceName} · {detail.sourceTier}
              </span>
              <span>·</span>
              <span className="font-mono">{detail.timeLabel}</span>
            </div>
            <h1 className="text-2xl font-extrabold leading-snug sm:text-3xl">{detail.title}</h1>
            {detail.tags?.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {detail.tags.map((tag) => (
                  <span key={tag} className="rounded border border-border bg-background/50 px-2.5 py-0.5 text-xs text-muted-foreground">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </GlassCard>

          <GlassCard>
            <div className="space-y-4">
              <div className="text-xs font-semibold text-primary">事实摘要</div>
              <p className="whitespace-pre-wrap text-sm leading-7 text-foreground/90">{detail.summary}</p>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4 text-xs">
                <span className="text-muted-foreground">核验出处：{detail.sourceName}</span>
                {originalHref ? (
                  <a
                    href={originalHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 font-medium text-primary hover:border-primary"
                  >
                    直达原始报道原文
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                ) : (
                  <span className="text-muted-foreground">原文链接暂缺</span>
                )}
              </div>
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
              <h2 className="text-base font-bold">事件后续 · {detail.followups.length}</h2>
              {detail.eventSummary && (
                <Link
                  to={`/finance/news/event/${detail.eventSummary.storyId}`}
                  className="inline-flex items-center gap-0.5 text-xs font-semibold text-primary hover:underline"
                >
                  查看完整事件
                  <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>

            {detail.followups.length > 0 ? (
              <div className="divide-y divide-border/50">
                {detail.followups.map((item) => {
                  const itemHref = safeHref(item.originalUrl);
                  const canNavigate = Boolean(detail.eventSummary);
                  return (
                    <div key={item.reportKey} className="flex flex-wrap items-center justify-between gap-3 py-3 text-xs">
                      <div className="flex min-w-0 flex-1 items-center gap-2.5">
                        <span className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">同事件</span>
                        {canNavigate ? (
                          <Link
                            to={`/finance/news/story/${item.reportKey}`}
                            className="truncate text-sm font-medium transition-colors hover:text-primary"
                          >
                            {item.title}
                          </Link>
                        ) : itemHref ? (
                          <a
                            href={itemHref}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="truncate text-sm font-medium transition-colors hover:text-primary"
                          >
                            {item.title}
                          </a>
                        ) : (
                          <span className="truncate text-sm font-medium">{item.title}</span>
                        )}
                      </div>
                      <span className="shrink-0 text-muted-foreground">
                        {item.sourceName} · {item.relativeTime}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="py-4 text-xs text-muted-foreground">
                目前仅收录当前这一篇核验报道；后续有新进展时会自动归入同事件时间轴。
              </p>
            )}
          </GlassCard>
        </article>
      ) : null}
    </div>
  );
}
