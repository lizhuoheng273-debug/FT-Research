import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BookOpen, ChevronDown, Loader2, PanelLeftClose, PanelLeftOpen, RefreshCw } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { UpcomingEvents } from "@/components/news/FinancialNewsPanels";
import {
  api,
  type FinancialCalendarResponse,
  type FinancialDailyEdition,
  type FinancialDailyEditionSummary,
} from "@/lib/api";

function safeUrl(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

function groupEditionsByMonth(items: FinancialDailyEditionSummary[]) {
  const groups = new Map<string, FinancialDailyEditionSummary[]>();
  for (const row of items) {
    const m = row.editionDate.match(/^(\d{4})-(\d{2})/);
    const label = m ? `${m[1]} 年 ${Number(m[2])} 月` : row.editionDate;
    groups.set(label, [...(groups.get(label) || []), row]);
  }
  return [...groups];
}

function currentBeijingEditionType(): "morning" | "evening" {
  const bjHour = new Date(Date.now() + 8 * 3600_000).getUTCHours();
  return bjHour >= 18 ? "evening" : "morning";
}

function initialRailOpen(): boolean {
  try {
    const saved = typeof window !== "undefined" && window.localStorage ? window.localStorage.getItem("ft_finance_daily_rail_open") : null;
    if (saved === "1") return true;
    if (saved === "0") return false;
    if (typeof window !== "undefined" && typeof window.innerWidth === "number") {
      return window.innerWidth >= 1440;
    }
  } catch {
    // Ignore storage access failures
  }
  return false;
}

function FinanceArchive({
  entries,
  activeKey,
  onSelect,
  onCollapse,
  compact = false,
}: {
  entries: FinancialDailyEditionSummary[];
  activeKey: string;
  onSelect: (key: string) => void;
  onCollapse?: () => void;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const groups = useMemo(() => groupEditionsByMonth(entries), [entries]);

  return (
    <aside className="edition-archive min-w-0">
      {!compact && (
        <div className="flex items-center justify-between px-2 py-2.5">
          <span className="text-sm font-semibold">往期</span>
          {onCollapse && (
            <button
              type="button"
              onClick={onCollapse}
              title="收起往期侧栏"
              aria-label="收起往期侧栏"
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-[var(--edition-muted)] transition-colors hover:bg-[var(--edition-tint)] hover:text-[var(--edition-accent)]"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
              <span>收起</span>
            </button>
          )}
        </div>
      )}
      {compact && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="finance-archive-entries"
          onClick={() => setExpanded((value) => !value)}
          className="flex w-full items-center justify-between border-b border-[var(--edition-line)] px-2 py-2 text-sm font-semibold"
        >
          往期 <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
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
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--edition-tint)] ${
                      active ? "bg-[var(--edition-tint)] text-[var(--edition-accent)]" : ""
                    }`}
                  >
                    <span className="w-6 shrink-0 text-center font-mono text-base font-semibold">{item.editionDate.slice(-2)}</span>
                    <span className="shrink-0 text-xs text-[var(--edition-muted)]">
                      {item.editionType === "morning" ? "早" : "晚"}
                    </span>
                    <span className="min-w-0 truncate text-xs">{item.leadTitle}</span>
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
  const [revision, setRevision] = useState(0);
  const [railOpen, setRailOpen] = useState<boolean>(initialRailOpen);

  const toggleRail = (next: boolean) => {
    setRailOpen(next);
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        window.localStorage.setItem("ft_finance_daily_rail_open", next ? "1" : "0");
      }
    } catch {
      // Ignore storage access failures
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    let timedOut = false;
    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 15000);
    setLoading(true);
    setError(null);

    let fallbackList: FinancialDailyEditionSummary[] = [];
    const listPromise = api
      .financialDailyEditions(controller.signal)
      .then((list) => {
        const safeList = Array.isArray(list) ? list : [];
        if (cancelled) return safeList;
        fallbackList = safeList;
        setEditions(safeList);
        return safeList;
      })
      .catch(() => [] as FinancialDailyEditionSummary[]);

    api
      .financialNewsCalendar(controller.signal)
      .then((cal) => {
        if (!cancelled && cal) setCalendar(cal);
      })
      .catch(() => undefined);

    const editionReq = requestedEditionKey
      ? api.financialDailyEdition(requestedEditionKey, controller.signal)
      : api.financialDailyLatest(requestedType, controller.signal);

    editionReq
      .then((ed) => {
        if (cancelled) return;
        if (ed && typeof ed === "object") {
          setEdition(ed);
        } else {
          setError("金融日报数据暂不可用，请重试");
        }
        setLoading(false);
      })
      .catch(async (reason) => {
        if (cancelled) return;
        if (timedOut) {
          const list = fallbackList.length > 0 ? fallbackList : await listPromise;
          if (cancelled) return;
          if (Array.isArray(list) && list.length > 0 && !requestedEditionKey) {
            try {
              const archived = await api.financialDailyEdition(list[0].editionKey);
              if (cancelled) return;
              if (archived && typeof archived === "object") {
                setEdition(archived);
                setError("最新排刊响应较慢，已先为您展示最近一期归档日报");
                setLoading(false);
                return;
              }
            } catch {
              // Fall through
            }
          }
          setError("加载金融日报超时，请点击重试或从左侧切换往期日报");
          setLoading(false);
          return;
        }
        setError(reason instanceof Error ? reason.message : "金融日报暂不可用");
        setLoading(false);
      })
      .finally(() => {
        window.clearTimeout(timeoutId);
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [requestedEditionKey, requestedType, revision]);

  useEffect(() => {
    if (!edition?.refreshing && !edition?.initializing) return;
    const baseGeneratedAt = edition.generatedAt;
    let active = true;
    let attempts = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      if (!active || attempts > 40) {
        window.clearInterval(timer);
        setRefreshing(false);
        return;
      }
      try {
        const next = requestedEditionKey
          ? await api.financialDailyEdition(requestedEditionKey)
          : await api.financialDailyLatest(requestedType);
        if (!active) return;
        if (next && typeof next === "object") {
          setEdition(next);
          if (!next.refreshing && !next.initializing) {
            window.clearInterval(timer);
            setRefreshing(false);
            if (next.generatedAt !== baseGeneratedAt) {
              setRefreshMessage("本期金融日报已更新");
              api.financialDailyEditions().then((l) => setEditions(Array.isArray(l) ? l : [])).catch(() => undefined);
            }
          }
        }
      } catch {
        // Ignore transient polling error
      }
    }, 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [edition?.refreshing, edition?.initializing, edition?.generatedAt, requestedEditionKey, requestedType]);

  const selectEditionKey = (key: string) => {
    setParams({ editionKey: key });
    document.querySelector("main")?.scrollTo(0, 0);
  };

  const switchEditionType = (type: "morning" | "evening") => {
    const currentDate = edition?.editionDate;
    const match = currentDate ? editions.find((item) => item.editionKey === `${currentDate}-${type}`) : undefined;
    if (match) {
      setParams({ editionKey: match.editionKey });
    } else {
      setParams({ edition: type });
    }
    document.querySelector("main")?.scrollTo(0, 0);
  };

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshMessage("正在更新信源并重新编排…");
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 60000);
    try {
      const targetType = edition?.editionType || requestedType;
      const [updated] = await Promise.all([
        api.financialDailyRefresh(targetType, controller.signal),
        api.financialNewsCalendarRefresh(controller.signal).catch(() => null),
      ]);
      setEdition(updated);
      if (updated?.refreshing) {
        setRefreshMessage("后台正在编排新版金融日报，完成后自动刷新…");
      } else {
        setRefreshMessage("本期金融日报与日程已更新");
        setRevision((value) => value + 1);
      }
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
  const requestedKeyType = requestedEditionKey.endsWith("-morning")
    ? "morning"
    : requestedEditionKey.endsWith("-evening")
      ? "evening"
      : undefined;
  const activeType = requestedKeyType || requestedType || edition?.editionType || currentBeijingEditionType();
  const activeSections = (edition?.sections || []).filter((sec) => (sec?.items || []).length > 0);
  const totalStories =
    edition?.storyCount ?? ((edition?.lead ? 1 : 0) + activeSections.reduce((sum, sec) => sum + (sec.items || []).length, 0));

  const aiContext = useMemo(
    () =>
      JSON.stringify(
        {
          source: "金融日报",
          editionKey: edition?.editionKey,
          dateLabel: edition?.dateLabel,
          lead: edition?.lead ? { title: edition.lead.title, summary: edition.lead.summary, source: edition.lead.sourceName } : null,
          sections: (edition?.sections || []).map((sec) => ({
            name: sec.name,
            items: (sec.items || []).map((item) => ({ title: item.title, summary: item.summary, source: item.sourceName })),
          })),
          upcomingEvents: calendarData?.items || [],
        },
        null,
        2,
      ),
    [edition, calendarData],
  );

  const leadOriginHref = safeUrl(edition?.lead?.originalUrl);

  return (
    <div className={`ai-report-paper min-h-[calc(100vh-1rem)] ${railOpen ? "" : "rail-collapsed"}`}>
      {editions.length > 0 && (
        <div className="edition-archive-rail">
          <div className="mb-2.5 inline-flex w-full gap-1 rounded-lg border border-[var(--edition-line)] bg-[var(--edition-surface)] p-0.5">
            {(["morning", "evening"] as const).map((val) => (
              <button
                key={val}
                type="button"
                aria-pressed={activeType === val}
                onClick={() => switchEditionType(val)}
                className={`flex-1 whitespace-nowrap rounded-md px-2 py-1.5 text-xs font-semibold transition-colors hover:text-[var(--edition-accent)] ${
                  activeType === val ? "bg-[var(--edition-tint)] text-[var(--edition-accent)]" : "text-[var(--edition-muted)]"
                }`}
              >
                {val === "morning" ? "早报 08:00" : "晚报 18:00"}
              </button>
            ))}
          </div>
          <FinanceArchive
            entries={editions}
            activeKey={edition?.editionKey || requestedEditionKey}
            onSelect={selectEditionKey}
            onCollapse={() => toggleRail(false)}
          />
        </div>
      )}

      <div className="edition-reading-area min-w-0">
        <div className="edition-reading-inner">
          {editions.length > 0 && (
            <div className="edition-reading-archive mb-4">
              <div className="mb-3 inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-[var(--edition-line)] bg-[var(--edition-surface)] p-0.5">
                {(["morning", "evening"] as const).map((val) => (
                  <button
                    key={val}
                    type="button"
                    aria-pressed={activeType === val}
                    onClick={() => switchEditionType(val)}
                    className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-semibold transition-colors hover:text-[var(--edition-accent)] ${
                      activeType === val ? "bg-[var(--edition-tint)] text-[var(--edition-accent)]" : "text-[var(--edition-muted)]"
                    }`}
                  >
                    {val === "morning" ? "早报 08:00" : "晚报 18:00"}
                  </button>
                ))}
              </div>
              <FinanceArchive compact entries={editions} activeKey={edition?.editionKey || requestedEditionKey} onSelect={selectEditionKey} />
            </div>
          )}

          {error && (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-l-2 border-warning bg-warning/10 px-3.5 py-2.5 text-xs text-muted-foreground">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setRevision((value) => value + 1)}
                className="inline-flex items-center gap-1 font-medium text-[var(--edition-accent)] hover:underline"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                重试
              </button>
            </div>
          )}

          {edition?.requestedEditionPending?.message && (
            <p className="mb-4 border-l-2 border-[var(--edition-accent)] bg-[var(--edition-tint)] px-3.5 py-2.5 text-xs text-[var(--edition-muted)]">
              {edition.requestedEditionPending.message}
            </p>
          )}

          {loading && !edition ? (
            <div className="flex items-center justify-center gap-2 py-24 text-sm text-[var(--edition-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在加载金融日报…
            </div>
          ) : edition ? (
            <article className="edition-report min-w-0">
              <header className="edition-masthead">
                <p className="text-xs text-[var(--edition-muted)]">
                  {edition.dateLabel} · {edition.publishTimeLabel}
                </p>
                <div className="edition-masthead-content flex items-center justify-between gap-4 py-5">
                  <div className="min-w-0">
                    <h1 className="edition-masthead-title text-3xl font-black tracking-tight">金融日报</h1>
                    <div className="mt-2.5 flex flex-wrap items-center gap-2">
                      {!railOpen && editions.length > 0 && (
                        <>
                          <button
                            type="button"
                            onClick={() => toggleRail(true)}
                            title="展开往期侧栏"
                            aria-label="展开往期侧栏"
                            className="hidden min-[1180px]:inline-flex items-center gap-1 rounded-md border border-[var(--edition-line)] px-2.5 py-1 text-xs text-[var(--edition-muted)] transition-colors hover:border-[var(--edition-accent)]/40 hover:text-[var(--edition-accent)]"
                          >
                            <PanelLeftOpen className="h-3.5 w-3.5" />
                            往期
                          </button>
                          <div className="hidden min-[1180px]:inline-flex gap-0.5 rounded-md border border-[var(--edition-line)] bg-[var(--edition-surface)] p-0.5">
                            {(["morning", "evening"] as const).map((val) => (
                              <button
                                key={val}
                                type="button"
                                aria-pressed={activeType === val}
                                onClick={() => switchEditionType(val)}
                                className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium transition-colors hover:text-[var(--edition-accent)] ${
                                  activeType === val ? "bg-[var(--edition-tint)] text-[var(--edition-accent)]" : "text-[var(--edition-muted)]"
                                }`}
                              >
                                {val === "morning" ? "早报" : "晚报"}
                              </button>
                            ))}
                          </div>
                        </>
                      )}
                      <AskAiButton
                        context={aiContext}
                        workspaceSource="news"
                        workspaceDate={edition.editionKey}
                        label="问 AI"
                        suggestions={[
                          "总结本期金融日报最核心的跨市场主线",
                          "梳理本期宏观政策与公司财报之间的关键联系",
                          "结合未来日程列出近期最值得跟踪的节点",
                        ]}
                      />
                      <button
                        type="button"
                        aria-label={refreshing ? "正在刷新金融日报" : "刷新金融日报"}
                        title="刷新金融日报"
                        aria-busy={refreshing}
                        disabled={refreshing}
                        onClick={() => void refresh()}
                        className="inline-flex items-center gap-1 rounded-md border border-[var(--edition-line)] px-2.5 py-1 text-xs text-[var(--edition-muted)] transition-colors hover:text-[var(--edition-accent)] disabled:opacity-50"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
                        更新
                      </button>
                      {refreshMessage && (
                        <span role="status" aria-live="polite" className="text-xs text-[var(--edition-muted)]">
                          {refreshMessage}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-baseline gap-1 border-l border-[var(--edition-line)] pl-3 font-mono text-[var(--edition-accent)] sm:pl-6">
                    <span className="text-3xl font-semibold leading-none sm:text-7xl">{edition.dayNumber}</span>
                    <span className="text-xs">{edition.editionTag}</span>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 border-y border-[var(--edition-line)] py-3 text-xs text-[var(--edition-muted)]">
                  <BookOpen className="h-3.5 w-3.5" />
                  <span>{totalStories} 件大事</span>
                </div>
              </header>

              {/* 头条 + 今日看点 + 本期版面（严格参照 AI 日报版式） */}
              <section className="edition-feature border-b border-[var(--edition-line)]">
                <div className="edition-headline-column min-w-0 py-7">
                  {edition.lead ? (
                    <>
                      <p className="text-xs font-bold tracking-wide text-[var(--edition-accent)]">头条</p>
                      <h2 className="edition-headline-title mt-3 break-words font-black">
                        <Link to={`/finance/news/story/${edition.lead.reportKey}`} className="transition-colors hover:text-[var(--edition-accent)]">
                          {edition.lead.title}
                        </Link>
                      </h2>
                      <p className="mt-4 min-w-0 break-words text-[15px] leading-[1.85] text-foreground/90">
                        {edition.lead.summary}
                      </p>
                      <div className="mt-4 flex flex-wrap items-center gap-4 text-xs">
                        <span className="text-[var(--edition-muted)]">{edition.lead.sourceName}</span>
                        <Link
                          to={`/finance/news/story/${edition.lead.reportKey}`}
                          className="font-medium text-[var(--edition-accent)] hover:underline"
                        >
                          阅读全文 →
                        </Link>
                        {leadOriginHref && (
                          <a
                            href={leadOriginHref}
                            rel="noreferrer"
                            target="_blank"
                            className="inline-flex items-center gap-0.5 text-[var(--edition-muted)] hover:text-[var(--edition-accent)]"
                          >
                            原文 <ArrowUpRight className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-[var(--edition-muted)]">本期暂无达到精选标准的头条新闻。</p>
                  )}
                </div>

                <aside className="edition-picks min-w-0 border-t border-[var(--edition-line)] py-7">
                  {(edition.keyPicks || []).length > 0 && (
                    <>
                      <h2 className="font-semibold">今日看点</h2>
                      <ol className="mt-1 divide-y divide-[var(--edition-line)]">
                        {(edition.keyPicks || []).map((pick, i) => (
                          <li key={pick.reportKey} className="flex items-start gap-2.5 py-3 text-sm leading-snug">
                            <span className="mt-0.5 shrink-0 font-mono text-[var(--edition-accent)]">{i + 1}</span>
                            <div className="min-w-0 flex-1">
                              <Link
                                to={`/finance/news/story/${pick.reportKey}`}
                                className="block font-medium transition-colors duration-150 hover:text-[var(--edition-accent)]"
                              >
                                {pick.title}
                              </Link>
                              {pick.summary && pick.summary !== pick.title && (
                                <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-[var(--edition-muted)]">
                                  {pick.summary}
                                </p>
                              )}
                            </div>
                          </li>
                        ))}
                      </ol>
                    </>
                  )}
                  <h2 className="mt-5 font-semibold">本期版面</h2>
                  <ol className="mt-1 text-sm">
                    {activeSections.map((sec, i) => (
                      <li key={sec.key}>
                        <a href={`#fin-sec-${sec.key}`} className="flex gap-2 py-1.5 transition-colors hover:text-[var(--edition-accent)]">
                          <span className="font-mono text-[var(--edition-accent)]">{String(i + 1).padStart(2, "0")}</span>
                          <span className="flex-1">{sec.name}</span>
                          <span className="text-[var(--edition-muted)]">{sec.items.length} 件</span>
                        </a>
                      </li>
                    ))}
                    <li>
                      <a href="#fin-sec-calendar" className="flex gap-2 py-1.5 transition-colors hover:text-[var(--edition-accent)]">
                        <span className="font-mono text-[var(--edition-accent)]">
                          {String(activeSections.length + 1).padStart(2, "0")}
                        </span>
                        <span className="flex-1">未来重要日程</span>
                        <span className="text-[var(--edition-muted)]">{calendarData?.items?.length || 0} 项</span>
                      </a>
                    </li>
                  </ol>
                </aside>
              </section>

              {/* 三大专题栏目：宏观数据与政策 / 市场表现 / 海外公司事件与财报 */}
              {activeSections.map((sec, i) => (
                <section id={`fin-sec-${sec.key}`} key={sec.key} className="edition-section scroll-mt-4">
                  <h2 className="edition-section-title flex items-baseline gap-3 border-b border-[var(--edition-line)] pb-3 font-black">
                    <span className="font-mono text-[var(--edition-accent)]">{String(i + 1).padStart(2, "0")}</span>
                    {sec.name}
                  </h2>
                  <div className="edition-section-stories grid">
                    {(sec.items || []).map((item) => {
                      const originHref = safeUrl(item.originalUrl);
                      return (
                        <article key={item.reportKey} className="edition-story min-w-0 border-b border-[var(--edition-line)] py-6">
                          <p className="truncate text-xs text-[var(--edition-muted)]">{item.sourceName}</p>
                          <h3 className="mt-2 break-words font-bold leading-normal">
                            <Link
                              to={`/finance/news/story/${item.reportKey}`}
                              className="transition-colors hover:text-[var(--edition-accent)]"
                            >
                              {item.title}
                            </Link>
                          </h3>
                          <p className="mt-2 break-words text-[15px] leading-[1.85] text-foreground/90">{item.summary}</p>
                          <div className="mt-3 flex items-center gap-4 text-xs">
                            <Link
                              to={`/finance/news/story/${item.reportKey}`}
                              className="font-medium text-[var(--edition-accent)] hover:underline"
                            >
                              {item.bucket === "market" ? "查看走势与详情" : item.bodyMode === "full" ? "阅读长文" : "查看详情"}
                            </Link>
                            {originHref && (
                              <a
                                href={originHref}
                                rel="noreferrer"
                                target="_blank"
                                className="inline-flex items-center gap-0.5 text-[var(--edition-muted)] hover:text-[var(--edition-accent)]"
                              >
                                原文 <ArrowUpRight className="h-3 w-3" />
                              </a>
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              ))}

              <section id="fin-sec-calendar" className="edition-section scroll-mt-4">
                <UpcomingEvents data={calendarData} loading={loading && !calendarData} error={null} />
              </section>

              <div className="pt-8">
                <Disclaimer />
              </div>
            </article>
          ) : null}
        </div>
      </div>
    </div>
  );
}
