import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, type FinancialTrackedEvent } from "@/lib/api";

type Tab = "overview" | "timeline" | "heat";

function safeHref(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

export function FinancialEventDetail() {
  const { storyId = "" } = useParams();
  const navigate = useNavigate();
  const [event, setEvent] = useState<FinancialTrackedEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .financialNewsTrackedEvent(storyId)
      .then(setEvent)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "事件脉络暂不可用"))
      .finally(() => setLoading(false));
  };

  useEffect(load, [storyId]);

  const context = useMemo(
    () =>
      event
        ? JSON.stringify(
            {
              source: "金融事件脉络",
              title: event.title,
              bucket: event.bucketName,
              overview: event.overview,
              whyHot: event.whyHot,
              milestones: event.milestones.map((m) => ({
                time: m.timeLabel,
                title: m.title,
                sources: m.sourceSummary,
                marketNote: m.marketNote,
              })),
              reports: event.reports.slice(0, 12).map((r) => ({
                title: r.title,
                source: r.sourceName,
                time: r.timeLabel,
                url: r.originalUrl,
              })),
            },
            null,
            2,
          )
        : "",
    [event],
  );

  const milestones = useMemo(() => {
    if (!event) return [];
    return sortOrder === "newest" ? event.milestones : [...event.milestones].reverse();
  }, [event, sortOrder]);

  const tabClass = (key: Tab) =>
    tab === key
      ? "rounded-lg bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground"
      : "rounded-lg border border-border bg-card px-3.5 py-1.5 text-xs text-muted-foreground hover:text-foreground";

  return (
    <div>
      <PageHeader
        title="事件追踪详情"
        subtitle="完整脉络 · 关键节点进展 · 精选报道时间线"
        actions={
          <div className="flex items-center gap-2">
            {event && (
              <AskAiButton
                context={context}
                workspaceSource="news-event"
                workspaceEventId={storyId}
                label="带入金融 AI（含完整脉络）"
                suggestions={[
                  "按时间脉络梳理这件事的关键转折点",
                  "哪些市场反应已被消化，后续还有哪些待验证数据？",
                  "汇总官方原文与各家权威媒体的核心差异",
                ]}
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

      {!event && loading ? (
        <p className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在加载完整事件脉络…
        </p>
      ) : event ? (
        <div className="mx-auto max-w-5xl space-y-5">
          <GlassCard glow>
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded bg-primary/15 px-2 py-0.5 font-semibold text-primary">{event.statusTag}</span>
              <span className="rounded border border-border bg-background/60 px-2 py-0.5 text-muted-foreground">
                {event.bucketName}
              </span>
            </div>
            <h1 className="text-2xl font-extrabold leading-snug sm:text-3xl">{event.title}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span>{event.reportCount} 篇精选报道</span>
              <span>·</span>
              <span>{event.sourceCount} 个独立来源</span>
              <span>·</span>
              <span>{event.firstReportLabel}</span>
              <span>·</span>
              <span>{event.latestUpdateLabel}</span>
            </div>
          </GlassCard>

          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => setTab("overview")} className={tabClass("overview")}>
              事件概览
            </button>
            <button type="button" onClick={() => setTab("timeline")} className={tabClass("timeline")}>
              报道时间线 ({event.reports.length})
            </button>
            <button type="button" onClick={() => setTab("heat")} className={tabClass("heat")}>
              热度趋势
            </button>
          </div>

          {tab === "overview" && (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
              <div className="space-y-5">
                {/* 先了解这件事 */}
                <GlassCard>
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <h2 className="text-base font-bold">先了解这件事</h2>
                    <span className="text-xs text-muted-foreground">客观整理 · 核验自全部出处</span>
                  </div>
                  <div className="space-y-3 text-sm leading-7 text-foreground/90">
                    {(event.overview?.paragraphs || []).map((para, idx) => (
                      <p key={idx}>{para}</p>
                    ))}
                  </div>
                  {event.overview?.latestMilestoneSummary && (
                    <div className="mt-4 border-t border-border/60 pt-3 text-xs">
                      <div className="font-semibold text-primary">最新进展</div>
                      <p className="mt-1 text-muted-foreground">{event.overview.latestMilestoneSummary}</p>
                    </div>
                  )}
                </GlassCard>

                {/* 事件进展（关键节点时间轴） */}
                <GlassCard>
                  <div className="mb-4 flex items-center justify-between gap-2">
                    <div>
                      <h2 className="text-base font-bold">事件进展</h2>
                      <p className="text-xs text-muted-foreground">{event.milestones.length} 个关键节点</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSortOrder((prev) => (prev === "newest" ? "oldest" : "newest"))}
                      className="rounded-lg border border-border bg-background/60 px-2.5 py-1 text-xs hover:border-primary"
                    >
                      {sortOrder === "newest" ? "最新在前 ▾" : "最早在前 ▾"}
                    </button>
                  </div>

                  <div className="relative space-y-5 pl-5 before:absolute before:bottom-2 before:left-[5px] before:top-2 before:w-px before:bg-border">
                    {milestones.map((ms, idx) => (
                      <div key={ms.milestoneId} className="relative space-y-2">
                        <span
                          className={`absolute -left-5 top-1.5 h-2.5 w-2.5 rounded-full ${
                            idx === 0 && sortOrder === "newest" ? "bg-primary" : "bg-muted-foreground"
                          }`}
                        />
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span className="font-mono font-medium text-foreground">{ms.timeLabel}</span>
                          <span>·</span>
                          <span>{ms.reportCount} 篇精选报道</span>
                        </div>
                        <Link
                          to={`/finance/news/story/${ms.representativeReportKey}`}
                          className="block text-sm font-bold leading-snug transition-colors hover:text-primary"
                        >
                          {ms.title}
                        </Link>
                        <div className="text-xs text-muted-foreground">{ms.sourceSummary}</div>
                        {ms.marketNote && (
                          <div className="rounded-lg border border-border/60 bg-background/40 px-3 py-2 text-xs text-muted-foreground">
                            {ms.marketNote}
                          </div>
                        )}
                        {ms.reports.length > 1 && (
                          <details className="pt-1">
                            <summary className="cursor-pointer select-none text-xs text-primary">
                              展开本节点全部 {ms.reports.length} 篇精选报道 ▾
                            </summary>
                            <div className="mt-2 space-y-1.5 border-l border-border pl-3">
                              {ms.reports.map((rep) => (
                                <Link
                                  key={rep.reportKey}
                                  to={`/finance/news/story/${rep.reportKey}`}
                                  className="block py-1 text-xs transition-colors hover:text-primary"
                                >
                                  <span className="mr-1.5 text-muted-foreground">[{rep.sourceName}]</span>
                                  {rep.title}
                                </Link>
                              ))}
                            </div>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                </GlassCard>
              </div>

              {/* 右侧边栏：为什么热 + 相关主题 + 事件记录 */}
              <aside className="space-y-4">
                <GlassCard>
                  <h3 className="text-sm font-bold">为什么热</h3>
                  <p className="mt-2 text-xs leading-6">{event.whyHot.headline}</p>
                  <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{event.whyHot.detail}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {event.whyHot.badges.map((badge) => (
                      <span key={badge} className="rounded bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                        {badge}
                      </span>
                    ))}
                  </div>
                </GlassCard>

                <GlassCard>
                  <h3 className="text-sm font-bold">相关主题与板块</h3>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {event.tags.map((tag) => (
                      <span key={tag} className="rounded border border-border bg-background/60 px-2.5 py-1 text-xs">
                        {tag}
                      </span>
                    ))}
                  </div>
                </GlassCard>

                <GlassCard>
                  <h3 className="text-sm font-bold">事件记录</h3>
                  <div className="mt-2.5 space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">首次报道</span>
                      <span className="font-mono">{event.recordMeta.firstAt}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">最新更新</span>
                      <span className="font-mono">{event.recordMeta.latestAt}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">关键节点</span>
                      <span className="font-mono">{event.recordMeta.nodeCount} 个</span>
                    </div>
                    <p className="border-t border-border/60 pt-2 leading-5 text-muted-foreground">
                      同一事件的连续进展会在 30 天内自动归并到本页时间轴，仅收录核验过的公开来源。
                    </p>
                  </div>
                </GlassCard>
              </aside>
            </div>
          )}

          {tab === "timeline" && (
            <GlassCard>
              <div className="mb-3 flex items-center justify-between border-b border-border/60 pb-3">
                <h2 className="text-base font-bold">该事件全部精选报道时间线</h2>
                <span className="text-xs text-muted-foreground">共 {event.reports.length} 篇核验报道</span>
              </div>
              <div className="divide-y divide-border/50">
                {event.reports.map((rep) => {
                  const href = safeHref(rep.originalUrl);
                  return (
                    <div key={rep.reportKey} className="flex flex-wrap items-start justify-between gap-3 py-3.5">
                      <div className="min-w-[240px] flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span className="font-mono">{rep.timeLabel}</span>
                          <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">{rep.sourceTier}</span>
                          <span>{rep.sourceName}</span>
                        </div>
                        <Link
                          to={`/finance/news/story/${rep.reportKey}`}
                          className="block text-sm font-semibold transition-colors hover:text-primary"
                        >
                          {rep.title}
                        </Link>
                      </div>
                      <div className="flex shrink-0 items-center gap-3 text-xs">
                        <Link to={`/finance/news/story/${rep.reportKey}`} className="text-primary hover:underline">
                          详情 →
                        </Link>
                        {href && (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                          >
                            原文
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </GlassCard>
          )}

          {tab === "heat" && (
            <GlassCard>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold">事件热度与关键节点走势</h2>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    按独立权威信源与 24 小时衰减窗口客观统计（已剔除重复转载）
                  </p>
                </div>
                <span className="rounded bg-primary/15 px-2.5 py-1 text-xs font-medium text-primary">
                  当前热度：{event.whyHot.heatIndex}
                </span>
              </div>

              {event.heatSeries.length > 0 ? (
                <>
                  <div
                    className="grid h-44 items-end gap-2 border-b border-border/60 pb-2 pt-4"
                    style={{ gridTemplateColumns: `repeat(${event.heatSeries.length}, minmax(0, 1fr))` }}
                  >
                    {(() => {
                      const maxVal = Math.max(...event.heatSeries.map((item) => item.value), 10);
                      return event.heatSeries.map((pt) => {
                        const heightPct = Math.max(12, Math.round((pt.value / maxVal) * 100));
                        return (
                          <div key={pt.label} className="flex h-full flex-col items-center justify-end gap-1.5">
                            <span className="font-mono text-xs text-muted-foreground">{pt.value}</span>
                            <div
                              className={`w-full max-w-[36px] rounded-t-md ${pt.milestone ? "bg-primary" : "bg-border"}`}
                              style={{ height: `${heightPct}%` }}
                            />
                            <span className="truncate font-mono text-[11px] text-muted-foreground">{pt.label}</span>
                          </div>
                        );
                      });
                    })()}
                  </div>
                  <div className="mt-4 space-y-2">
                    <div className="text-xs font-semibold text-muted-foreground">热度节点标注</div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {event.heatSeries
                        .filter((item) => item.milestone)
                        .map((item) => (
                          <div
                            key={`${item.label}-${item.milestone}`}
                            className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-background/40 px-3 py-2 text-xs"
                          >
                            <span className="truncate font-medium">{item.milestone}</span>
                            <span className="shrink-0 font-mono text-primary">
                              {item.label} · {item.value}
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="py-6 text-xs text-muted-foreground">热度样本积累中，随后续报道与小时快照自动生成走势。</p>
              )}
            </GlassCard>
          )}
        </div>
      ) : null}
    </div>
  );
}
