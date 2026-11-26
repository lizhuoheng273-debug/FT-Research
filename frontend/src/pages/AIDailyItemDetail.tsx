import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowUpRight, ChevronDown, ChevronRight, List, Loader2, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { apiUrl, authHeaders } from "@/lib/api";

interface OutlineEntry {
  id: string;
  text: string;
  level: number;
}

interface AiDailyItemData {
  id: string;
  title: string;
  originalTitle?: string;
  sourceName: string;
  publishedAt?: string;
  score?: number | null;
  digest?: string;
  reason?: string;
  lang?: "zh" | "original";
  bodyMode?: "full" | "summary";
  bodyLabel?: string;
  hasOriginalLang?: boolean;
  bodyMarkdown?: string;
  outline?: OutlineEntry[];
  tags?: string[];
  originalUrl?: string;
  aihotUrl?: string;
  story?: { storyId: string; title: string } | null;
  dailyEdition?: { date: string; label: string } | null;
}

interface FallbackStory {
  id?: string;
  title?: string;
  summary?: string;
  publishedAt?: string;
  source?: { name?: string };
  links?: { aihot?: string; original?: string };
}

function safeHref(value?: string | null) {
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

function nodeText(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(nodeText).join("");
  if (children && typeof children === "object" && "props" in children) {
    return nodeText((children as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

function fromFallback(itemId: string, fb?: FallbackStory): AiDailyItemData | null {
  if (!fb?.title) return null;
  return {
    id: itemId,
    title: fb.title,
    sourceName: fb.source?.name || "AI HOT",
    publishedAt: fb.publishedAt || "",
    digest: fb.summary || "",
    originalUrl: fb.links?.original || "",
    aihotUrl: fb.links?.aihot || "",
    bodyMode: "summary",
    bodyMarkdown: "",
    outline: [],
    tags: [],
  };
}

export function AIDailyItemDetail() {
  const { itemId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fallback = (location.state as { fallback?: FallbackStory } | null)?.fallback;
  const [lang, setLang] = useState<"zh" | "original">("zh");
  const [detail, setDetail] = useState<AiDailyItemData | null>(() => fromFallback(itemId, fallback));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [tocOpen, setTocOpen] = useState(false);

  useEffect(() => {
    setLang("zh");
    setDetail(fromFallback(itemId, fallback));
  }, [itemId]);

  useEffect(() => {
    if (!itemId) {
      setError("缺少资讯编号");
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(apiUrl(`/ai/reports/items/${encodeURIComponent(itemId)}?lang=${lang}`), {
      headers: authHeaders(),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(res.status === 404 ? "该资讯详情不存在" : "资讯详情暂不可用");
        return res.json() as Promise<AiDailyItemData>;
      })
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((reason: unknown) => {
        if (cancelled || (reason instanceof Error && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "资讯详情暂不可用");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [itemId, lang, revision]);

  const context = useMemo(
    () =>
      detail
        ? JSON.stringify(
            {
              source: "AI 日报",
              title: detail.title,
              media: detail.sourceName,
              publishedAt: detail.publishedAt,
              digest: detail.digest,
              reason: detail.reason,
              body: detail.bodyMarkdown ? detail.bodyMarkdown.slice(0, 2600) : undefined,
              originalUrl: detail.originalUrl,
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

  const headingIdMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of outline) map.set(entry.text.trim(), entry.id);
    return map;
  }, [outline]);

  return (
    <div className="min-h-[calc(100vh-1rem)] px-4 py-6 sm:px-8 sm:py-9">
      <div className={`mx-auto ${hasToc ? "max-w-[1040px]" : "max-w-[740px]"}`}>
        {/* 顶栏导航：与金融日报保持一致的克制扁平样式 */}
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--edition-line)] pb-4 text-xs">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-[var(--edition-muted)] transition-colors duration-150 hover:text-[var(--edition-accent)]"
          >
            <ArrowLeft className="h-4 w-4" />
            返回 AI 日报
          </button>
          <div className="flex flex-wrap items-center gap-3">
            {detail && (
              <AskAiButton
                context={context}
                workspaceSource="ai-news"
                workspaceEventId={itemId}
                workspaceSnapshot={{
                  title: detail.title,
                  summary: detail.digest || "",
                  originalUrl: detail.originalUrl || "",
                }}
                label="针对此条问 AI"
                suggestions={["这件事最核心的技术/产业影响是什么？", "拆解正文里的关键数据与看点", "对相关 AI 赛道与上市公司有哪些启发？"]}
              />
            )}
            {originalHref && (
              <a
                href={originalHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[var(--edition-muted)] transition-colors duration-150 hover:text-[var(--edition-accent)]"
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
            <button
              type="button"
              onClick={() => setRevision((v) => v + 1)}
              className="inline-flex items-center gap-1 text-xs font-medium text-[var(--edition-accent)] hover:underline"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              重试
            </button>
          </div>
        )}

        {!detail && loading ? (
          <p className="flex items-center justify-center gap-2 py-20 text-sm text-[var(--edition-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在加载站内详情…
          </p>
        ) : detail ? (
          <div className={hasToc ? "grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_220px]" : ""}>
            <article className="min-w-0">
              <header className="border-b border-[var(--edition-line)] pb-6">
                <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--edition-muted)]">
                  <span className="font-semibold text-[var(--edition-accent)]">{detail.sourceName}</span>
                  {detail.publishedAt && (
                    <>
                      <span className="opacity-45">·</span>
                      <span className="font-mono">{detail.publishedAt}</span>
                    </>
                  )}
                  {detail.score != null && (
                    <>
                      <span className="opacity-45">·</span>
                      <span className="rounded bg-[var(--edition-tint)] px-1.5 py-0.5 font-mono text-[11px] font-medium text-[var(--edition-accent)]">
                        AI 评分 {detail.score}
                      </span>
                    </>
                  )}
                </div>
                <h1 className="mt-3 text-2xl font-black leading-[1.34] tracking-tight sm:text-[31px]">
                  {detail.title}
                </h1>
                {detail.originalTitle && detail.originalTitle !== detail.title && (
                  <p className="mt-2 text-xs leading-relaxed text-[var(--edition-muted)]">{detail.originalTitle}</p>
                )}
              </header>

              {/* 移动端目录 */}
              {hasToc && (
                <div className="mt-5 border-b border-[var(--edition-line)] pb-4 lg:hidden">
                  <button
                    type="button"
                    onClick={() => setTocOpen((v) => !v)}
                    className="flex w-full items-center justify-between text-xs font-semibold text-[var(--edition-muted)] transition-colors hover:text-[var(--edition-accent)]"
                  >
                    <span className="inline-flex items-center gap-1.5">
                      <List className="h-3.5 w-3.5 text-[var(--edition-accent)]" />
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
                          className={`block py-0.5 text-[var(--edition-muted)] transition-colors hover:text-[var(--edition-accent)] ${item.level === 3 ? "pl-3" : ""}`}
                        >
                          {item.text}
                        </a>
                      ))}
                    </nav>
                  )}
                </div>
              )}

              {/* AI 导读 + 推荐理由 */}
              {detail.digest && (
                <section className="mt-6 rounded-r-lg border-l-2 border-[var(--edition-accent)] bg-[var(--edition-tint)] px-5 py-4">
                  <p className="text-xs font-semibold tracking-wide text-[var(--edition-accent)]">AI 导读</p>
                  <p className="mt-2 whitespace-pre-wrap text-[15px] leading-[1.9] text-foreground/95">
                    {detail.digest}
                  </p>
                  {detail.reason && (
                    <p className="mt-3 border-t border-[var(--edition-line)] pt-2.5 text-xs leading-relaxed text-[var(--edition-muted)]">
                      <span className="font-medium text-foreground/80">推荐理由：</span>
                      {detail.reason}
                    </p>
                  )}
                </section>
              )}

              {/* 正文（含站内 中文 / 原文 切换） */}
              {hasFullBody ? (
                <section className="mt-8 border-t border-[var(--edition-line)] pt-6">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <span className="text-xs text-[var(--edition-muted)]">{detail.bodyLabel || "正文"}</span>
                    {detail.hasOriginalLang && (
                      <div className="inline-flex gap-0.5 rounded-full border border-[var(--edition-line)] bg-[var(--edition-surface)] p-0.5 text-xs">
                        {(["zh", "original"] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            onClick={() => setLang(mode)}
                            className={`rounded-full px-3 py-1 transition-colors ${
                              lang === mode
                                ? "bg-[var(--edition-tint)] font-medium text-[var(--edition-accent)]"
                                : "text-[var(--edition-muted)] hover:text-foreground"
                            }`}
                          >
                            {mode === "zh" ? "中文" : "原文"}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {loading ? (
                    <p className="flex items-center gap-2 py-8 text-xs text-[var(--edition-muted)]">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      正在切换语言版本…
                    </p>
                  ) : (
                    <div className="prose prose-sm max-w-none leading-[1.95] text-foreground/90 dark:prose-invert sm:prose-base">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h2: ({ children }) => {
                            const text = nodeText(children).trim();
                            const id = headingIdMap.get(text);
                            return (
                              <h2 id={id} className="mt-9 scroll-mt-6 border-b border-[var(--edition-line)] pb-2 text-lg font-bold">
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
                          p: ({ children }) => <p className="my-4 text-[15px] leading-[1.95]">{children}</p>,
                        }}
                      >
                        {detail.bodyMarkdown || ""}
                      </ReactMarkdown>
                    </div>
                  )}
                </section>
              ) : loading ? (
                <p className="mt-6 flex items-center gap-2 text-xs text-[var(--edition-muted)]">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  正在获取完整正文与关联事件…
                </p>
              ) : null}

              {/* 所属事件（站内直达 /ai/news/story/:storyId，不跳站外） */}
              {detail.story?.storyId && (
                <section className="mt-9 border-t border-[var(--edition-line)] pt-6">
                  <div className="mb-2 flex items-baseline justify-between gap-3">
                    <span className="text-xs font-semibold text-[var(--edition-muted)]">所属事件</span>
                    <Link
                      to={`/ai/news/story/${detail.story.storyId}`}
                      className="inline-flex items-center gap-0.5 text-xs font-medium text-[var(--edition-accent)] hover:underline"
                    >
                      查看完整事件
                      <ChevronRight className="h-3.5 w-3.5" />
                    </Link>
                  </div>
                  <Link
                    to={`/ai/news/story/${detail.story.storyId}`}
                    className="block text-base font-bold leading-snug text-foreground transition-colors duration-150 hover:text-[var(--edition-accent)]"
                  >
                    {detail.story.title}
                  </Link>
                </section>
              )}

              {/* 标签与来源脚注 */}
              <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--edition-line)] pt-5 text-xs text-[var(--edition-muted)]">
                <div className="flex flex-wrap items-center gap-2">
                  <span>来源：{detail.sourceName}</span>
                  {detail.dailyEdition?.date && (
                    <Link
                      to={`/ai/daily?kind=daily&period=${detail.dailyEdition.date}`}
                      className="rounded bg-[var(--edition-tint)] px-2 py-0.5 text-[var(--edition-accent)] hover:underline"
                    >
                      {detail.dailyEdition.label}
                    </Link>
                  )}
                  {(detail.tags || []).map((tag) => (
                    <span key={tag} className="rounded border border-[var(--edition-line)] px-2 py-0.5">
                      {tag}
                    </span>
                  ))}
                </div>
                {originalHref && (
                  <a
                    href={originalHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-[var(--edition-accent)] hover:underline"
                  >
                    直达原始报道原文
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </a>
                )}
              </footer>
            </article>

            {/* 桌面端长文目录右侧栏 */}
            {hasToc && (
              <aside className="hidden lg:block">
                <div className="sticky top-6 border-l border-[var(--edition-line)] pl-4">
                  <div className="mb-3 text-xs font-semibold text-[var(--edition-accent)]">目录</div>
                  <nav className="space-y-2 text-xs">
                    {outline.map((item) => (
                      <a
                        key={item.id}
                        href={`#${item.id}`}
                        className={`block leading-snug text-[var(--edition-muted)] transition-colors duration-150 hover:text-[var(--edition-accent)] ${
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
