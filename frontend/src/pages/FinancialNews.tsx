import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, Loader2, RefreshCw } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { UpcomingEvents } from "@/components/news/FinancialNewsPanels";
import {
  api,
  type FinancialCalendarResponse,
  type FinancialDailyEdition,
  type FinancialDailyEditionSummary,
} from "@/lib/api";

function groupEditionsByMonth(items: FinancialDailyEditionSummary[]) {
  const groups = new Map<string, FinancialDailyEditionSummary[]>();
  for (const row of items) {
    const m = row.editionDate.match(/^(\d{4})-(\d{2})/);
    const label = m ? `${m[1]} 年 ${Number(m[2])} 月` : row.editionDate;
    groups.set(label, [...(groups.get(label) || []), row]);
  }
  return [...groups];
}

function FinanceArchive({
  entries,
  activeKey,
  onSelect,
  compact = false,
}: {
  entries: FinancialDailyEditionSummary[];
  activeKey: string;
  onSelect: (key: string) => void;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const groups = useMemo(() => groupEditionsByMonth(entries), [entries]);

  return (
    <aside className="edition-archive min-w-0">
      {!compact && <div className="px-2 py-3 text-sm font-semibold">往期金融日报</div>}
      {compact && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="finance-archive-entries"
          onClick={() => setExpanded((value) => !value)}
          className="flex w-full items-center justify-between border-b border-[var(--edition-line)] px-2 py-2 text-sm font-semibold"
        >
          往期日报 <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
      )}
      <div
        id={compact ? "finance-archive-entries" : undefined}
        hidden={compact && !expanded}
        className="edition-archive-entries max-h-48 overflow-y-auto pt-2"
      >
        {groups.map(([label, items], index) => (
          <details key={label} open={index === 0 || items.some((item) => item.editionKey === activeKey)} className="mb-1">
            <summary className="flex cursor-pointer list-none justify-between rounded-md px-2 py-2 text-xs text-[var(--edition-muted)]">
              <span>{label}</span>
              <span>{items.length}</span>
            </summary>
            <div className="space-y-0.5">
              {items.map((item) => {
                const active = item.editionKey === activeKey;
                return (
                  <button
                    type="button"
                    key={item.editionKey}
                    onClick={() => {
                      onSelect(item.editionKey);
                      setExpanded(false);
                    }}
                    title={item.leadTitle}
                    aria-current={active ? "date" : undefined}
                    className={`flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--edition-tint)] ${
                      active ? "bg-[var(--edition-tint)] text-[var(--edition-accent)]" : ""
                    }`}
                  >
                    <div className="w-7 shrink-0 text-center">
                      <div className="font-mono text-sm font-semibold leading-tight">{item.editionDate.slice(-2)}</div>
                      <div className="text-[11px] text-[var(--edition-muted)]">
                        {item.editionType === "morning" ? "早报" : "晚报"}
                      </div>
                    </div>
                    <span className="min-w-0 line-clamp-2 text-xs leading-snug">{item.leadTitle}</span>
                  </button>
                );
              })}
            </div>
          </details>
        ))}
      </div>
    </aside>
  );
}

export function FinancialNews() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requestedEditionKey = params.get("editionKey") || "";
  const requestedTypeParam = params.get("edition");
  const requestedType = requestedTypeParam === "morning" || requestedTypeParam === "evening" ? requestedTypeParam : undefined;

  const [edition, setEdition] = useState<FinancialDailyEdition | null>(null);
  const [editions, setEditions] = useState<FinancialDailyEditionSummary[]>([]);
  const [calendar, setCalendar] = useState<FinancialCalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState("");
  const [urgentDismissed, setUrgentDismissed] = useState(false);
  const [showCoverage, setShowCoverage] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const editionReq = requestedEditionKey
      ? api.financialDailyEdition(requestedEditionKey, controller.signal)
      : api.financialDailyLatest(requestedType, controller.signal);

    Promise.allSettled([
      editionReq,
      api.financialDailyEditions(controller.signal),
      api.financialNewsCalendar(controller.signal),
    ]).then(([edRes, listRes, calRes]) => {
      if (controller.signal.aborted) return;
      if (edRes.status === "fulfilled") {
        setEdition(edRes.value);
      } else {
        setError(edRes.reason instanceof Error ? edRes.reason.message : "金融日报暂不可用");
      }
      if (listRes.status === "fulfilled") setEditions(listRes.value);
      if (calRes.status === "fulfilled") setCalendar(calRes.value);
      setLoading(false);
    });

    return () => controller.abort();
  }, [requestedEditionKey, requestedType, revision]);

  const selectEditionKey = (key: string) => {
    setUrgentDismissed(false);
    setParams({ editionKey: key });
  };

  const switchEditionType = (type: "morning" | "evening") => {
    setUrgentDismissed(false);
    const currentDate = edition?.editionDate;
    const match = currentDate ? editions.find((item) => item.editionKey === `${currentDate}-${type}`) : undefined;
    if (match) {
      setParams({ editionKey: match.editionKey });
    } else {
      setParams({ edition: type });
    }
  };

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshMessage("正在更新各路信源并重新编排日报…");
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 60000);
    try {
      const targetType = edition?.editionType || requestedType;
      const [updated] = await Promise.all([
        api.financialDailyRefresh(targetType, controller.signal),
        api.financialNewsCalendarRefresh(controller.signal).catch(() => null),
      ]);
      setEdition(updated);
      setUrgentDismissed(false);
      setRefreshMessage("本期金融日报与日程已更新");
      setRevision((value) => value + 1);
    } catch (reason) {
      setRefreshMessage(
        controller.signal.aborted
          ? "刷新超时，请稍后重试"
          : reason instanceof Error
            ? reason.message
            : "刷新失败，请稍后重试",
      );
    } finally {
      window.clearTimeout(timer);
      setRefreshing(false);
    }
  };

  const calendarData = calendar || edition?.calendar || null;
  const activeType = edition?.editionType || requestedType || "evening";
  const aiContext = useMemo(
    () =>
      JSON.stringify(
        {
          source: "金融日报",
          editionKey: edition?.editionKey,
          dateLabel: edition?.dateLabel,
          overview: edition?.overview,
          lead: edition?.lead,
          keyPicks: edition?.keyPicks,
          sections: (edition?.sections || []).map((sec) => ({
            name: sec.name,
            items: sec.items.map((item) => ({ title: item.title, source: item.sourceName, publishedAt: item.publishedAt })),
          })),
          upcomingEvents: calendarData?.items || [],
        },
        null,
        2,
      ),
    [edition, calendarData],
  );

  const activeSections = (edition?.sections || []).filter((sec) => sec.items.length > 0);
  const urgent = edition?.urgentBanner;

  return (
    <div className="ai-report-paper min-h-[calc(100vh-1rem)]">
      {editions.length > 0 && (
        <div className="edition-archive-rail">
          <FinanceArchive entries={editions} activeKey={edition?.editionKey || requestedEditionKey} onSelect={selectEditionKey} />
        </div>
      )}

      <div className="edition-reading-area">
        <div className="edition-reading-inner space-y-6">
          {editions.length > 0 && (
            <div className="edition-reading-archive mb-4">
              <FinanceArchive entries={editions} activeKey={edition?.editionKey || requestedEditionKey} onSelect={selectEditionKey} compact />
            </div>
          )}

          {urgent && !urgentDismissed && (
            <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3">
              <div className="min-w-[220px] flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="rounded bg-warning px-1.5 py-0.5 font-semibold text-primary-foreground">实时突发</span>
                  <span className="font-mono">{urgent.time}</span>
                  <span>来源：{urgent.sourceName}</span>
                </div>
                <button
                  type="button"
                  onClick={() => navigate(`/finance/news/story/${urgent.reportKey}`)}
                  className="text-left text-sm font-semibold transition-colors hover:text-primary"
                >
                  {urgent.title}
                </button>
              </div>
              <div className="flex shrink-0 items-center gap-2 text-xs">
                <Link
                  to={`/finance/news/story/${urgent.reportKey}`}
                  className="rounded-lg border border-border bg-card px-2.5 py-1 hover:border-primary"
                >
                  查看详情
                </Link>
                <Link
                  to={`/finance/news/event/${urgent.storyId}`}
                  className="rounded-lg bg-primary/15 px-2.5 py-1 font-medium text-primary hover:bg-primary/25"
                >
                  事件脉络
                </Link>
                <button
                  type="button"
                  onClick={() => setUrgentDismissed(true)}
                  className="px-1 text-muted-foreground hover:text-foreground"
                >
                  收起
                </button>
              </div>
            </div>
          )}

          {error && (
            <p className="rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm text-muted-foreground">
              {error}
            </p>
          )}

          {loading && !edition ? (
            <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在加载金融日报…
            </div>
          ) : edition ? (
            <article className="edition-report min-w-0 space-y-6">
              <header className="edition-masthead border-b border-[var(--edition-line)] pb-5">
                <p className="text-xs text-[var(--edition-muted)]">
                  <span className="font-mono">{edition.dateLabel}</span> · {edition.publishTimeLabel}
                </p>
                <div className="edition-masthead-content flex flex-wrap items-center justify-between gap-4 py-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="edition-masthead-title text-3xl font-black tracking-tight">金融日报</h1>
                    <div className="inline-flex rounded-lg border border-[var(--edition-line)] bg-[var(--edition-surface)] p-0.5 text-xs">
                      <button
                        type="button"
                        onClick={() => switchEditionType("morning")}
                        className={`rounded-md px-3 py-1 transition-colors ${
                          activeType === "morning"
                            ? "bg-primary font-semibold text-primary-foreground"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        早报 08:00
                      </button>
                      <button
                        type="button"
                        onClick={() => switchEditionType("evening")}
                        className={`rounded-md px-3 py-1 transition-colors ${
                          activeType === "evening"
                            ? "bg-primary font-semibold text-primary-foreground"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        晚报 18:00
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <AskAiButton
                      context={aiContext}
                      workspaceSource="news"
                      workspaceDate={edition.editionKey}
                      label="问 AI"
                      suggestions={[
                        "总结本期金融日报最核心的跨市场主线",
                        "结合本期新闻和未来两周日程列出重点节点",
                        "梳理哪些信息还有待进一步官方数据验证",
                      ]}
                    />
                    {refreshMessage && (
                      <span role="status" aria-live="polite" className="max-w-44 text-right text-xs text-muted-foreground">
                        {refreshMessage}
                      </span>
                    )}
                    <button
                      type="button"
                      aria-label={refreshing ? "正在刷新金融日报" : "刷新金融日报"}
                      title="刷新金融日报"
                      aria-busy={refreshing}
                      disabled={refreshing}
                      onClick={() => void refresh()}
                      className="rounded-lg border border-border p-2 hover:text-primary disabled:opacity-50"
                    >
                      <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
                    </button>
                    <div className="hidden items-baseline gap-1 border-l border-[var(--edition-line)] pl-4 font-mono text-[var(--edition-accent)] sm:flex">
                      <span className="text-5xl font-semibold leading-none">{edition.dayNumber}</span>
                      <span className="text-xs text-[var(--edition-muted)]">{edition.editionTag}</span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--edition-line)] pt-3 text-xs text-[var(--edition-muted)]">
                  <span>
                    {edition.coverage
                      ? `本期精选 ${edition.coverage.selectedCount} 条 · 归并自 ${edition.coverage.rawReports} 条原始快讯与 ${edition.coverage.activeSources}/${edition.coverage.totalSources} 个可用信源`
                      : "早晚双刊 · 客观聚合"}
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowCoverage((value) => !value)}
                    className="underline decoration-dotted underline-offset-4 hover:text-foreground"
                  >
                    {showCoverage ? "收起来源覆盖与缺口 ▴" : "查看来源覆盖与缺口 ▾"}
                  </button>
                </div>

                {showCoverage && edition.coverage && (
                  <div className="mt-3 grid gap-2 rounded-xl border border-border bg-card p-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
                    {edition.coverage.sources.map((src) => (
                      <div key={src.name} className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-background/40 px-2.5 py-1.5">
                        <span className="truncate">{src.name}</span>
                        <span className={src.ok ? "shrink-0 text-success" : "shrink-0 text-warning"}>
                          {src.ok ? `${src.count} 条` : src.cache === "stale" ? "缓存" : "暂不可用"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </header>

              {edition.marketStrip && (
                <section className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span className="font-semibold">{edition.marketStrip.title}</span>
                    <span>{edition.marketStrip.note}</span>
                  </div>
                  {edition.marketStrip.items.length > 0 ? (
                    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                      {edition.marketStrip.items.map((item) => (
                        <div key={item.name} className="rounded-xl border border-border bg-card px-3 py-2.5">
                          <div className="text-xs text-muted-foreground">{item.name}</div>
                          <div className="mt-0.5 font-mono text-base font-bold">{item.value}</div>
                          <div
                            className={`mt-0.5 font-mono text-xs ${
                              item.direction === "up"
                                ? "text-primary"
                                : item.direction === "down"
                                  ? "text-success"
                                  : "text-muted-foreground"
                            }`}
                          >
                            {item.change}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2.5 text-xs text-muted-foreground">
                      <AlertTriangle className="h-3.5 w-3.5 text-warning" />
                      {edition.marketStrip.note}
                    </p>
                  )}
                </section>
              )}

              <section className="border-l-2 border-[var(--edition-accent)] bg-[var(--edition-tint)] px-4 py-3">
                <h2 className="text-xs font-bold text-[var(--edition-accent)]">本期导读</h2>
                <p className="mt-1 text-sm leading-7">{edition.overview}</p>
              </section>

              <section className="edition-feature border-b border-[var(--edition-line)] pb-6">
                <div className="edition-headline-column min-w-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-semibold tracking-wider text-[var(--edition-accent)]">今日金融头条</span>
                    {edition.lead && (
                      <Link
                        to={`/finance/news/event/${edition.lead.storyId}`}
                        className="text-xs font-medium text-[var(--edition-accent)] hover:underline"
                      >
                        持续事件 · {edition.lead.milestoneCount} 个关键节点 / {edition.lead.reportCount} 篇报道 &gt;
                      </Link>
                    )}
                  </div>

                  {edition.lead ? (
                    <article className="mt-3 space-y-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">
                          {edition.lead.sectionName || edition.lead.bucket}
                        </span>
                        <span>{edition.lead.sourceName}</span>
                        {edition.lead.relativeTime && (
                          <>
                            <span>·</span>
                            <span className="font-mono">{edition.lead.relativeTime}</span>
                          </>
                        )}
                      </div>
                      <h2 className="edition-headline-title font-extrabold tracking-tight">
                        <Link
                          to={`/finance/news/story/${edition.lead.reportKey}`}
                          className="transition-colors hover:text-[var(--edition-accent)]"
                        >
                          {edition.lead.title}
                        </Link>
                      </h2>
                      <p className="text-sm leading-7 text-muted-foreground">{edition.lead.summary}</p>
                      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                        <div className="flex flex-wrap gap-1.5">
                          {(edition.lead.tags || []).map((tag) => (
                            <span key={tag} className="rounded border border-border bg-card px-2 py-0.5 text-xs text-muted-foreground">
                              {tag}
                            </span>
                          ))}
                        </div>
                        <div className="flex items-center gap-3 text-xs font-medium">
                          <Link to={`/finance/news/story/${edition.lead.reportKey}`} className="text-primary hover:underline">
                            阅读详情 →
                          </Link>
                          <Link
                            to={`/finance/news/event/${edition.lead.storyId}`}
                            className="rounded-lg bg-primary/10 px-2.5 py-1 text-primary hover:bg-primary/20"
                          >
                            查看完整事件 &gt;
                          </Link>
                        </div>
                      </div>
                    </article>
                  ) : (
                    <p className="mt-4 text-sm text-muted-foreground">暂无满足本期准入标准的头条新闻。</p>
                  )}
                </div>

                <aside className="edition-picks space-y-6 border-t border-[var(--edition-line)] pt-6 lg:border-t-0">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="font-semibold tracking-wider">本期看点</span>
                      <span>精选自各版面</span>
                    </div>
                    {edition.keyPicks.length > 0 ? (
                      <ol className="space-y-3 text-xs leading-relaxed">
                        {edition.keyPicks.map((pick, index) => (
                          <li key={pick.reportKey}>
                            <Link
                              to={`/finance/news/story/${pick.reportKey}`}
                              className="group flex items-start gap-2.5 rounded-lg p-1.5 -mx-1.5 transition-colors hover:bg-card"
                            >
                              <span className="mt-0.5 shrink-0 font-mono font-bold text-primary">0{index + 1}</span>
                              <div className="space-y-1">
                                <span className="inline-block rounded border border-border bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground">
                                  {pick.sectionName}
                                </span>
                                <p className="font-medium text-foreground transition-colors group-hover:text-primary">
                                  {pick.title}
                                </p>
                              </div>
                            </Link>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="text-xs text-muted-foreground">本期各版面暂无更多看点。</p>
                    )}
                  </div>

                  <div className="space-y-2 border-t border-[var(--edition-line)] pt-4">
                    <div className="text-xs font-semibold tracking-wider text-muted-foreground">本期版面</div>
                    <div className="space-y-1 text-xs">
                      {activeSections.map((sec) => (
                        <a
                          key={sec.key}
                          href={`#fin-sec-${sec.key}`}
                          className="flex items-center justify-between rounded px-2 py-1.5 transition-colors hover:bg-card"
                        >
                          <span>
                            <span className="mr-2 font-mono text-primary">{sec.code}</span>
                            {sec.name}
                          </span>
                          <span className="font-mono text-muted-foreground">{sec.items.length}</span>
                        </a>
                      ))}
                      <a
                        href="#fin-sec-calendar"
                        className="flex items-center justify-between rounded px-2 py-1.5 transition-colors hover:bg-card"
                      >
                        <span>
                          <span className="mr-2 font-mono text-primary">06</span>未来重要日程
                        </span>
                        <span className="font-mono text-muted-foreground">{calendarData?.items?.length || 0}</span>
                      </a>
                    </div>
                  </div>
                </aside>
              </section>

              <div className="space-y-10">
                {activeSections.map((sec) => (
                  <section key={sec.key} id={`fin-sec-${sec.key}`} className="space-y-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--edition-line)] pb-2">
                      <div className="flex items-baseline gap-2.5">
                        <span className="font-mono text-sm font-bold text-primary">{sec.code}</span>
                        <h2 className="edition-section-title font-bold">{sec.name}</h2>
                      </div>
                      <span className="text-xs text-muted-foreground">{sec.note}</span>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      {sec.items.map((item) => (
                        <Link
                          key={item.reportKey}
                          to={`/finance/news/story/${item.reportKey}`}
                          className="group flex flex-col justify-between space-y-2.5 rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary"
                        >
                          <div className="space-y-2">
                            <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                              <span>
                                {item.sourceName} · <span className="font-mono">{item.relativeTime || "近期"}</span>
                              </span>
                              {item.milestoneCount > 1 || item.reportCount > 1 ? (
                                <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">
                                  同事件 {item.milestoneCount} 节点 / {item.reportCount} 篇
                                </span>
                              ) : null}
                            </div>
                            <h3 className="text-sm font-bold leading-snug transition-colors group-hover:text-primary">
                              {item.title}
                            </h3>
                            <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">{item.summary}</p>
                          </div>
                          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
                            <div className="flex flex-wrap gap-1.5">
                              {(item.tags || []).slice(0, 3).map((tag) => (
                                <span key={tag} className="rounded border border-border bg-background px-2 py-0.5 text-muted-foreground">
                                  {tag}
                                </span>
                              ))}
                            </div>
                            <span className="text-primary">进入详情 →</span>
                          </div>
                        </Link>
                      ))}
                    </div>
                  </section>
                ))}
              </div>

              <section id="fin-sec-calendar" className="pt-4">
                <UpcomingEvents data={calendarData} loading={loading && !calendarData} error={null} />
              </section>

              <Disclaimer />
            </article>
          ) : null}
        </div>
      </div>
    </div>
  );
}
