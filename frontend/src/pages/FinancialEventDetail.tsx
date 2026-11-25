import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowUpRight, Loader2, RefreshCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Disclaimer } from "@/components/ui/Disclaimer";
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
      ? "border-b-2 border-[var(--edition-accent)] pb-2.5 text-sm font-semibold text-foreground"
      : "pb-2.5 text-sm text-[var(--edition-muted)] hover:text-foreground";

  return (
    <div className="min-h-[calc(100vh-1rem)] px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto max-w-[1020px]">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--edition-line)] pb-4 text-xs">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-[var(--edition-muted)] transition-colors hover:text-[var(--edition-accent)]"
          >
            <ArrowLeft className="h-4 w-4" />
            返回
          </button>
          {event && (
            <AskAiButton
              context={context}
              workspaceSource="news-event"
              workspaceEventId={storyId}
              label="带入金融 AI（含完整脉络）"
              suggestions={[
                "按时间脉络梳理这件事的关键转折点",
                "哪些市场反应已被消化，后续还有哪些待验证数据？",
              ]}
            />
          )}
        </div>

        {error && (
          <div className="mb-6 flex items-center justify-between border-l-2 border-warning bg-warning/10 px-4 py-3 text-sm text-muted-foreground">
            <span>{error}</span>
            <button type="button" onClick={load} className="inline-flex items-center gap-1 text-xs font-medium text-[var(--edition-accent)] hover:underline">
              <RefreshCw className="h-3.5 w-3.5" />
              重试
            </button>
          </div>
        )}

        {!event && loading ? (
          <p className="flex items-center justify-center gap-2 py-20 text-sm text-[var(--edition-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在加载完整事件脉络…
          </p>
        ) : event ? (
          <div>
            <header className="pb-6">
              <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--edition-muted)]">
                <span className="font-semibold text-[var(--edition-accent)]">{event.bucketName}</span>
                <span>·</span>
                <span>{event.statusTag}</span>
              </div>
              <h1 className="mt-2.5 text-2xl font-black leading-snug sm:text-3xl">{event.title}</h1>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-[var(--edition-muted)]">
                <span>{event.milestones.length} 个进展节点</span>
                <span>·</span>
                <span>{event.reportCount} 篇精选报道</span>
                <span>·</span>
                <span>{event.sourceCount} 个独立来源</span>
                <span>·</span>
                <span>{event.firstReportLabel}</span>
              </div>
            </header>

            <div className="mb-8 flex items-center gap-6 border-b border-[var(--edition-line)]">
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
              <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_260px]">
                <div className="min-w-0 space-y-10">
                  <section>
                    <h2 className="mb-3 text-base font-bold">先了解这件事</h2>
                    <div className="space-y-3 border-l-2 border-[var(--edition-accent)] bg-[var(--edition-tint)] px-4 py-3.5 text-[15px] leading-[1.85] text-foreground/95">
                      {(event.overview?.paragraphs || []).map((para, idx) => (
                        <p key={idx}>{para}</p>
                      ))}
                    </div>
                  </section>

                  <section className="border-t border-[var(--edition-line)] pt-6">
                    <div className="mb-5 flex items-center justify-between gap-2">
                      <h2 className="text-base font-bold">事件进展（{event.milestones.length} 个节点）</h2>
                      <button
                        type="button"
                        onClick={() => setSortOrder((prev) => (prev === "newest" ? "oldest" : "newest"))}
                        className="text-xs text-[var(--edition-muted)] hover:text-[var(--edition-accent)]"
                      >
                        {sortOrder === "newest" ? "最新在前 ▾" : "最早在前 ▾"}
                      </button>
                    </div>

                    <div className="relative space-y-6 pl-5 before:absolute before:bottom-2 before:left-[5px] before:top-2 before:w-px before:bg-[var(--edition-line)]">
                      {milestones.map((ms, idx) => (
                        <div key={ms.milestoneId} className="relative space-y-1.5">
                          <span
                            className={`absolute -left-5 top-1.5 h-2.5 w-2.5 rounded-full ${
                              idx === 0 && sortOrder === "newest" ? "bg-[var(--edition-accent)]" : "bg-[var(--edition-muted)]"
                            }`}
                          />
                          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--edition-muted)]">
                            <span className="font-mono font-medium text-foreground">{ms.timeLabel}</span>
                            <span>·</span>
                            <span>{ms.sourceSummary}</span>
                          </div>
                          <Link
                            to={`/finance/news/story/${ms.representativeReportKey}`}
                            className="block text-base font-bold leading-snug transition-colors hover:text-[var(--edition-accent)]"
                          >
                            {ms.title}
                          </Link>
                          {ms.reports.length > 1 && (
                            <details className="pt-1">
                              <summary className="cursor-pointer select-none text-xs text-[var(--edition-accent)]">
                                查看同节点 {ms.reports.length} 家媒体报道 ▾
                              </summary>
                              <div className="mt-2 space-y-1.5 border-l border-[var(--edition-line)] pl-3">
                                {ms.reports.map((rep) => (
                                  <Link
                                    key={rep.reportKey}
                                    to={`/finance/news/story/${rep.reportKey}`}
                                    className="block py-0.5 text-xs text-[var(--edition-muted)] hover:text-[var(--edition-accent)]"
                                  >
                                    [{rep.sourceName}] {rep.title}
                                  </Link>
                                ))}
                              </div>
                            </details>
                          )}
                        </div>
                      ))}
                    </div>
                  </section>
                </div>

                <aside className="space-y-6 border-t border-[var(--edition-line)] pt-6 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
                  <div>
                    <h3 className="text-xs font-bold text-[var(--edition-muted)]">为什么热</h3>
                    <p className="mt-2 text-xs leading-6">{event.whyHot.headline}</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--edition-muted)]">{event.whyHot.detail}</p>
                  </div>
                  <div className="border-t border-[var(--edition-line)] pt-5">
                    <h3 className="text-xs font-bold text-[var(--edition-muted)]">事件记录</h3>
                    <div className="mt-2.5 space-y-2 text-xs">
                      <div className="flex justify-between">
                        <span className="text-[var(--edition-muted)]">首次报道</span>
                        <span className="font-mono">{event.recordMeta.firstAt}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--edition-muted)]">最新更新</span>
                        <span className="font-mono">{event.recordMeta.latestAt}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--edition-muted)]">进展节点</span>
                        <span className="font-mono">{event.recordMeta.nodeCount} 个</span>
                      </div>
                    </div>
                  </div>
                </aside>
              </div>
            )}

            {tab === "timeline" && (
              <div className="divide-y divide-[var(--edition-line)]">
                {event.reports.map((rep) => {
                  const href = safeHref(rep.originalUrl);
                  return (
                    <div key={rep.reportKey} className="flex flex-wrap items-baseline justify-between gap-3 py-4">
                      <div className="min-w-[240px] flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--edition-muted)]">
                          <span className="font-mono">{rep.timeLabel}</span>
                          <span>·</span>
                          <span>{rep.sourceName}</span>
                        </div>
                        <Link
                          to={`/finance/news/story/${rep.reportKey}`}
                          className="block text-sm font-semibold transition-colors hover:text-[var(--edition-accent)]"
                        >
                          {rep.title}
                        </Link>
                      </div>
                      <div className="flex shrink-0 items-center gap-3 text-xs">
                        <Link to={`/finance/news/story/${rep.reportKey}`} className="text-[var(--edition-accent)] hover:underline">
                          详情
                        </Link>
                        {href && (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-0.5 text-[var(--edition-muted)] hover:text-foreground"
                          >
                            原文 <ArrowUpRight className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {tab === "heat" && (
              <div>
                <div className="mb-4 flex items-baseline justify-between gap-2">
                  <p className="text-xs text-[var(--edition-muted)]">
                    按独立信源与 24 小时衰减窗口客观统计（已剔除重复转载）
                  </p>
                  <span className="font-mono text-xs font-semibold text-[var(--edition-accent)]">
                    当前热度：{event.whyHot.heatIndex}
                  </span>
                </div>
                {event.heatSeries.length > 0 ? (
                  <div
                    className="grid h-44 items-end gap-2 border-b border-[var(--edition-line)] pb-2 pt-4"
                    style={{ gridTemplateColumns: `repeat(${event.heatSeries.length}, minmax(0, 1fr))` }}
                  >
                    {(() => {
                      const maxVal = Math.max(...event.heatSeries.map((item) => item.value), 10);
                      return event.heatSeries.map((pt) => {
                        const heightPct = Math.max(12, Math.round((pt.value / maxVal) * 100));
                        return (
                          <div key={pt.label} className="flex h-full flex-col items-center justify-end gap-1.5">
                            <span className="font-mono text-xs text-[var(--edition-muted)]">{pt.value}</span>
                            <div
                              className={`w-full max-w-[36px] rounded-t-sm ${pt.milestone ? "bg-[var(--edition-accent)]" : "bg-border"}`}
                              style={{ height: `${heightPct}%` }}
                            />
                            <span className="truncate font-mono text-[11px] text-[var(--edition-muted)]">{pt.label}</span>
                          </div>
                        );
                      });
                    })()}
                  </div>
                ) : (
                  <p className="py-6 text-xs text-[var(--edition-muted)]">热度样本积累中。</p>
                )}
              </div>
            )}

            <div className="mt-10">
              <Disclaimer />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
