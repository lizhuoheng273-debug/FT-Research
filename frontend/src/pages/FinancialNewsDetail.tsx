import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowUpRight, ChevronDown, ChevronRight, List, Loader2, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { MarketChart } from "@/components/market/MarketChart";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Disclaimer } from "@/components/ui/Disclaimer";
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
  return {
    reportKey: item.id,
    title: item.title,
    summary: (isHot ? item.aiDigest : legacy.summary || legacy.aiDigest) || item.title,
    bodyMode: "summary",
    bodyMarkdown: "",
    outline: [],
    marketChart: null,
    publishedAt: item.publishedAt,
    timeLabel: item.publishedAt ? item.publishedAt.slice(0, 16).replace("T", " ") : "近期",
    relativeTime: "近期",
    sourceName: isHot ? placements[0]?.sourceName || "平台热榜" : legacy.source || "公开来源",
    sourceTier: isHot ? "平台要闻" : "公开报道",
    originalUrl: item.originalUrl || placements[0]?.originalUrl || "",
    bucket: "macro",
    bucketName: isHot ? "财经要闻" : legacy.category || "财经资讯",
    eventSummary: null,
    followups: [],
  };
}

function nodeText(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(nodeText).join("");
  if (children && typeof children === "object" && "props" in children) {
    return nodeText((children as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

export function FinancialNewsDetail() {
  const { eventId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fallback = (location.state as { fallback?: LegacyStory } | null)?.fallback;
  const [detail, setDetail] = useState<FinancialReportDetail | null>(fallback ? adaptLegacy(fallback) : null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tocOpen, setTocOpen] = useState(false);

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
              body: detail.bodyMarkdown ? detail.bodyMarkdown.slice(0, 2400) : undefined,
              originalUrl: detail.originalUrl,
              event: detail.eventSummary,
              followups: (detail.followups || []).slice(0, 6),
            },
            null,
            2,
          )
        : "",
    [detail],
  );

  const originalHref = safeHref(detail?.originalUrl);
  const outline = detail?.bodyMode === "full" && Array.isArray(detail?.outline) ? detail.outline : [];
  const hasToc = outline.length >= 2;
  const hasFullBody = detail?.bodyMode === "full" && Boolean(detail?.bodyMarkdown?.trim());
  const followups = detail?.followups || [];

  // Map heading text -> outline id so markdown h2/h3 anchors match TOC links deterministically
  const headingIdMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of outline) {
      map.set(entry.text.trim(), entry.id);
    }
    return map;
  }, [outline]);

  return (
    <div className="min-h-[calc(100vh-1rem)] px-4 py-6 sm:px-8 sm:py-8">
      <div className={`mx-auto ${hasToc ? "max-w-[1020px]" : "max-w-[740px]"}`}>
        {/* 顶栏导航：简洁扁平，去卡片割裂感 */}
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--edition-line)] pb-4 text-xs">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-[var(--edition-muted)] transition-colors hover:text-[var(--edition-accent)]"
          >
            <ArrowLeft className="h-4 w-4" />
            返回金融日报
          </button>
          <div className="flex flex-wrap items-center gap-3">
            {detail && (
              <AskAiButton
                context={context}
                workspaceSource="news-story"
                workspaceEventId={eventId}
                label="针对此条问 AI"
                suggestions={["这件事最核心的市场影响是什么？", "拆解原文中的关键数据与逻辑", "还有哪些后续数据需要验证？"]}
              />
            )}
            {originalHref && (
              <a
                href={originalHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[var(--edition-muted)] transition-colors hover:text-[var(--edition-accent)]"
              >
                原文
                <ArrowUpRight className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
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

        {!detail && loading ? (
          <p className="flex items-center justify-center gap-2 py-20 text-sm text-[var(--edition-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在加载正文…
          </p>
        ) : detail ? (
          <div className={hasToc ? "grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_220px]" : ""}>
            <article className="min-w-0">
              {/* 新闻报头 */}
              <header className="border-b border-[var(--edition-line)] pb-6">
                <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--edition-muted)]">
                  <span className="font-semibold text-[var(--edition-accent)]">{detail.bucketName}</span>
                  <span>·</span>
                  <span>{detail.sourceName}</span>
                  <span>·</span>
                  <span className="font-mono">{detail.timeLabel}</span>
                </div>
                <h1 className="mt-3 text-2xl font-black leading-[1.32] tracking-tight sm:text-[32px]">
                  {detail.title}
                </h1>
                {detail.originalTitle && detail.originalTitle !== detail.title && (
                  <p className="mt-2 text-xs leading-relaxed text-[var(--edition-muted)]">{detail.originalTitle}</p>
                )}
              </header>

              {/* 移动端长文目录折叠条 */}
              {hasToc && (
                <div className="mt-6 border-b border-[var(--edition-line)] pb-4 lg:hidden">
                  <button
                    type="button"
                    onClick={() => setTocOpen((v) => !v)}
                    className="flex w-full items-center justify-between text-xs font-semibold text-[var(--edition-muted)]"
                  >
                    <span className="inline-flex items-center gap-1.5">
                      <List className="h-3.5 w-3.5" />
                      本文目录（{outline.length} 节）
                    </span>
                    <ChevronDown className={`h-4 w-4 transition-transform ${tocOpen ? "rotate-180" : ""}`} />
                  </button>
                  {tocOpen && (
                    <nav className="mt-3 space-y-1.5 border-l border-[var(--edition-line)] pl-3 text-xs">
                      {outline.map((item) => (
                        <a
                          key={item.id}
                          href={`#${item.id}`}
                          onClick={() => setTocOpen(false)}
                          className={`block py-0.5 text-[var(--edition-muted)] hover:text-[var(--edition-accent)] ${item.level === 3 ? "pl-3" : ""}`}
                        >
                          {item.text}
                        </a>
                      ))}
                    </nav>
                  )}
                </div>
              )}

              {/* 答案前置核心摘要（平铺阅读风格，不套浮动卡片） */}
              <section className="mt-6 border-l-2 border-[var(--edition-accent)] bg-[var(--edition-tint)] px-4 py-3.5">
                <p className="text-xs font-semibold text-[var(--edition-accent)]">核心摘要</p>
                <p className="mt-1.5 whitespace-pre-wrap text-[15px] leading-[1.85] text-foreground/95">
                  {detail.summary}
                </p>
              </section>

              {/* 市场表现类资讯：直接内嵌站内相关市场交互式 K 线图 */}
              {detail.marketChart && (
                <section className="mt-8 border-t border-[var(--edition-line)] pt-6">
                  <div className="mb-3 flex items-baseline justify-between gap-2">
                    <h2 className="text-base font-bold">{detail.marketChart.name} 走势图</h2>
                    <span className="font-mono text-xs text-[var(--edition-muted)]">{detail.marketChart.code}</span>
                  </div>
                  <MarketChart
                    asset={detail.marketChart.asset}
                    code={detail.marketChart.code}
                    defaultPeriod="daily"
                  />
                </section>
              )}

              {/* 中文完整正文（仅当原文相对摘要有实质细节增量时展示） */}
              {hasFullBody && (
                <section className="mt-8 border-t border-[var(--edition-line)] pt-6">
                  <div className="prose prose-sm max-w-none leading-[1.9] text-foreground/90 dark:prose-invert sm:prose-base">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h2: ({ children }) => {
                          const text = nodeText(children).trim();
                          const id = headingIdMap.get(text);
                          return (
                            <h2 id={id} className="mt-8 scroll-mt-6 border-b border-[var(--edition-line)] pb-2 text-lg font-bold">
                              {children}
                            </h2>
                          );
                        },
                        h3: ({ children }) => {
                          const text = nodeText(children).trim();
                          const id = headingIdMap.get(text);
                          return (
                            <h3 id={id} className="mt-6 scroll-mt-6 text-base font-bold">
                              {children}
                            </h3>
                          );
                        },
                        p: ({ children }) => <p className="my-4 text-[15px] leading-[1.9]">{children}</p>,
                      }}
                    >
                      {detail.bodyMarkdown || ""}
                    </ReactMarkdown>
                  </div>
                </section>
              )}

              {/* 底部出处直达 */}
              <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--edition-line)] pt-5 text-xs text-[var(--edition-muted)]">
                <span>来源：{detail.sourceName}</span>
                {originalHref ? (
                  <a
                    href={originalHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-[var(--edition-accent)] hover:underline"
                  >
                    直达原始报道原文
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </a>
                ) : (
                  <span>原文链接暂缺</span>
                )}
              </footer>

              {/* 事件后续（参照 AIHOT：只有真正存在增量新节点时才显示；没有则整块不渲染） */}
              {followups.length > 0 && (
                <section className="mt-10 border-t border-[var(--edition-line)] pt-6">
                  <div className="mb-3 flex items-baseline justify-between gap-3">
                    <h2 className="text-sm font-bold">
                      事件后续 <span className="font-mono font-normal text-[var(--edition-muted)]">· {followups.length}</span>
                    </h2>
                    {detail.eventSummary && (
                      <Link
                        to={`/finance/news/event/${detail.eventSummary.storyId}`}
                        className="inline-flex items-center gap-0.5 text-xs font-medium text-[var(--edition-accent)] hover:underline"
                      >
                        查看完整事件
                        <ChevronRight className="h-3.5 w-3.5" />
                      </Link>
                    )}
                  </div>
                  <div className="divide-y divide-[var(--edition-line)]">
                    {followups.map((item) => (
                      <div key={item.reportKey} className="flex flex-wrap items-baseline justify-between gap-3 py-3 text-sm">
                        <div className="flex min-w-0 flex-1 items-baseline gap-2.5">
                          <span className="shrink-0 font-mono text-xs text-[var(--edition-accent)]">
                            {item.timeLabel || item.relativeTime}
                          </span>
                          <Link
                            to={`/finance/news/story/${item.reportKey}`}
                            className="min-w-0 font-medium transition-colors hover:text-[var(--edition-accent)]"
                          >
                            {item.title}
                          </Link>
                        </div>
                        <span className="shrink-0 text-xs text-[var(--edition-muted)]">{item.sourceName}</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <div className="mt-10">
                <Disclaimer />
              </div>
            </article>

            {/* 桌面端长文目录右侧栏 */}
            {hasToc && (
              <aside className="hidden lg:block">
                <div className="sticky top-6 border-l border-[var(--edition-line)] pl-4">
                  <div className="mb-3 text-xs font-semibold text-[var(--edition-muted)]">目录</div>
                  <nav className="space-y-2 text-xs">
                    {outline.map((item) => (
                      <a
                        key={item.id}
                        href={`#${item.id}`}
                        className={`block leading-snug text-[var(--edition-muted)] transition-colors hover:text-[var(--edition-accent)] ${
                          item.level === 3 ? "pl-3" : ""
                        }`}
                      >
                        {item.text}
                      </a>
                    ))}
                  </nav>
                </div>
              </aside>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
