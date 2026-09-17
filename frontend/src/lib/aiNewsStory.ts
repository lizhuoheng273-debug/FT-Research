import { apiUrl, authHeaders } from "@/lib/api";

export interface StoryLinks {
  aihot?: string;
  original?: string;
  story?: string;
}

export interface HotFeedItem {
  id?: string;
  title?: string;
  summary?: string;
  reason?: string;
  category?: string;
  score?: number;
  source?: string | { name?: string };
  publishedAt?: string;
  links?: StoryLinks;
  originalUrl?: string;
}

export interface HotFeedTopic extends HotFeedItem {
  id: string;
}

export interface AiNewsStoryReport {
  title?: string;
  summary?: string;
  source?: string | { name?: string };
  publishedAt?: string;
  links?: { original?: string };
}

export interface AiNewsStorySnapshot {
  title?: string;
  summary?: string;
  latest?: string;
  originalUrl?: string;
}

export interface Story {
  title?: string;
  digest?: string;
  latest?: string;
  links?: { original?: string };
  reports?: AiNewsStoryReport[];
  [key: string]: unknown;
}

type StoryFetcher = (storyId: string, signal?: AbortSignal) => Promise<unknown>;

export interface LoadAiNewsStoryOptions {
  signal?: AbortSignal;
  fetcher?: StoryFetcher;
  retries?: number;
  retryDelayMs?: number;
}

export interface PrefetchAiNewsStoryOptions extends LoadAiNewsStoryOptions {
  now?: () => number;
  prefetchTtlMs?: number;
}

export interface TakePrefetchedAiNewsStoryOptions {
  now?: () => number;
}

const PREFETCH_CACHE_LIMIT = 10;
const PREFETCH_TTL_MS = 30_000;
export const AI_NEWS_STORY_CONTEXT_LIMIT = 18_000;
const TITLE_LIMIT = 500;
const DIGEST_LIMIT = 5_000;
const LATEST_LIMIT = 3_000;
const REPORT_LIMIT = 1_000;
const REPORTS_LIMIT = 7_000;
const LINK_LIMIT = 500;
const LINKS_LIMIT = 2_000;

interface PrefetchedStoryEntry {
  promise: Promise<Story>;
  expiresAt: number;
}

const prefetchedStories = new Map<string, PrefetchedStoryEntry>();

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object";

const truncate = (value: unknown, limit: number, fallback = "暂无") => {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return fallback;
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1))}…`;
};

const boundedSection = (label: string, values: string[], limit: number) => {
  const prefix = `${label}：`;
  if (!values.length) return `${prefix}暂无`;
  let section = prefix;
  for (const value of values) {
    const separator = section === prefix ? "" : "\n";
    if (section.length + separator.length + value.length > limit) break;
    section += separator + value;
  }
  return section === prefix ? `${prefix}${truncate(values[0], Math.max(1, limit - prefix.length))}` : section;
};

export function buildAiNewsStoryContext(story: Story = {}, snapshot?: AiNewsStorySnapshot): { title: string; text: string } {
  const reports = Array.isArray(story.reports) ? story.reports : [];
  const title = truncate(story.title || snapshot?.title, TITLE_LIMIT, "未命名热点");
  const digest = truncate(story.digest || snapshot?.summary, DIGEST_LIMIT);
  const latest = truncate(story.latest || snapshot?.latest, LATEST_LIMIT);
  const reportRows = reports.map((report, index) => {
    const reportSource = typeof report.source === "string" ? report.source : report.source?.name;
    const row = [
      `${index + 1}. ${truncate(report.title, 300, "未命名报道")}`,
      truncate(report.summary, 500, ""),
      truncate(reportSource, 100, ""),
      truncate(report.publishedAt, 80, ""),
    ].filter(Boolean).join("｜");
    return truncate(row, REPORT_LIMIT, "");
  }).filter(Boolean);
  const originalLinks = [...new Set([
    story.links?.original,
    ...reports.map((report) => report.links?.original),
    snapshot?.originalUrl,
  ].filter((link): link is string => Boolean(link)))].map((link) => truncate(link, LINK_LIMIT, "")).filter(Boolean);
  const text = [
    "来源：AI 热点资讯",
    `标题：${title}`,
    `AI 摘要：${digest}`,
    `最新进展：${latest}`,
    boundedSection("来源报道", reportRows, REPORTS_LIMIT),
    boundedSection("原文链接", originalLinks, LINKS_LIMIT),
  ].join("\n");
  return { title, text: truncate(text, AI_NEWS_STORY_CONTEXT_LIMIT, "") };
}

const publicIdFromLink = (link?: string) => {
  if (!link) return "";
  try {
    const pathname = new URL(link, "http://localhost").pathname.replace(/\/+$/, "");
    const segment = pathname.split("/").filter(Boolean).pop();
    return segment ? decodeURIComponent(segment) : "";
  } catch {
    const segment = link.split(/[?#]/, 1)[0].split("/").filter(Boolean).pop();
    return segment || "";
  }
};

const normalizeTitle = (title?: string) => String(title || "")
  .normalize("NFKC")
  .toLocaleLowerCase()
  .replace(/[\p{P}\p{S}\s]+/gu, "");

const abortError = () => new DOMException("The operation was aborted", "AbortError");

const isAbortError = (error: unknown) => isRecord(error) && error.name === "AbortError";

const throwIfAborted = (signal?: AbortSignal) => {
  if (signal?.aborted) throw abortError();
};

const waitForRetry = (delayMs: number, signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
  throwIfAborted(signal);
  const timer = setTimeout(() => {
    signal?.removeEventListener("abort", onAbort);
    resolve();
  }, delayMs);
  const onAbort = () => {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
    reject(abortError());
  };
  signal?.addEventListener("abort", onAbort, { once: true });
});

const withAbort = <T>(promise: Promise<T>, signal?: AbortSignal) => {
  if (!signal) return promise;
  throwIfAborted(signal);
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const cleanup = () => signal.removeEventListener("abort", onAbort);
    const onAbort = () => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(abortError());
    };
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then((value) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(value);
    }, (error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    });
  });
};

const defaultFetcher: StoryFetcher = async (storyId, signal) => {
  const response = await fetch(apiUrl(`/ai/news/stories/${encodeURIComponent(storyId)}`), {
    signal,
    headers: authHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json() as { detail?: string };
      message = body.detail || message;
    } catch {
      // Keep the HTTP status when the error response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
};

const storyFromPayload = async (payload: unknown): Promise<Story> => {
  let body = payload;
  if (isRecord(body) && typeof body.json === "function") {
    if (body.ok === false) throw new Error(`HTTP ${String(body.status || "error")}`);
    body = await (body.json as () => Promise<unknown>)();
  }
  if (isRecord(body) && isRecord(body.story)) return body.story as Story;
  if (isRecord(body)) return body as Story;
  throw new Error("AI HOT 详情返回格式无效");
};

export function storyPublicId(topic: HotFeedTopic, item?: HotFeedItem): string {
  return publicIdFromLink(topic.links?.story) || publicIdFromLink(item?.links?.story) || topic.id;
}

export function findStoryFallback(topic: HotFeedTopic, items: HotFeedItem[]): HotFeedItem | undefined {
  const topicStoryId = publicIdFromLink(topic.links?.story);
  if (topicStoryId) {
    const storyMatch = items.find((candidate) => publicIdFromLink(candidate.links?.story) === topicStoryId);
    if (storyMatch) return storyMatch;
  }

  const topicOriginal = topic.links?.original;
  if (topicOriginal) {
    const originalMatch = items.find((candidate) => (candidate.links?.original || candidate.originalUrl) === topicOriginal);
    if (originalMatch) return originalMatch;
  }

  const idMatch = items.find((candidate) => candidate.id === topic.id);
  if (idMatch) return idMatch;

  const normalizedTopicTitle = normalizeTitle(topic.title);
  if (!normalizedTopicTitle) return undefined;
  return items.find((candidate) => normalizeTitle(candidate.title) === normalizedTopicTitle);
}

export async function loadAiNewsStory(storyId: string, options: LoadAiNewsStoryOptions = {}): Promise<Story> {
  const signal = options.signal;
  const fetcher = options.fetcher || defaultFetcher;
  const retries = Math.max(0, Math.floor(options.retries ?? 2));
  const retryDelayMs = Math.max(0, options.retryDelayMs ?? 150);
  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    throwIfAborted(signal);
    try {
      const payload = await withAbort(Promise.resolve().then(() => fetcher(storyId, signal)), signal);
      return await storyFromPayload(payload);
    } catch (error) {
      if (isAbortError(error) || signal?.aborted) throw signal?.aborted && !isAbortError(error) ? abortError() : error;
      lastError = error;
      if (attempt >= retries) throw error;
      await waitForRetry(retryDelayMs * (attempt + 1), signal);
    }
  }
  throw lastError || new Error("AI HOT 详情加载失败");
}

export function prefetchAiNewsStory(storyId: string, options: PrefetchAiNewsStoryOptions = {}): Promise<Story> {
  const now = options.now || Date.now;
  const existing = prefetchedStories.get(storyId);
  if (existing && existing.expiresAt > now()) return existing.promise;
  if (existing) prefetchedStories.delete(storyId);

  const ttlMs = Math.max(0, options.prefetchTtlMs ?? PREFETCH_TTL_MS);
  const entry: PrefetchedStoryEntry = { promise: Promise.resolve({}), expiresAt: Number.POSITIVE_INFINITY };
  const promise = loadAiNewsStory(storyId, options).then((story) => {
    if (prefetchedStories.get(storyId) === entry) entry.expiresAt = now() + ttlMs;
    return story;
  });
  entry.promise = promise;
  prefetchedStories.set(storyId, entry);
  while (prefetchedStories.size > PREFETCH_CACHE_LIMIT) {
    const oldest = prefetchedStories.keys().next().value as string | undefined;
    if (!oldest) break;
    prefetchedStories.delete(oldest);
  }
  void promise.catch(() => {
    if (prefetchedStories.get(storyId) === entry) prefetchedStories.delete(storyId);
  });
  return promise;
}

export function takePrefetchedAiNewsStory(storyId: string, options: TakePrefetchedAiNewsStoryOptions = {}): Promise<Story> | undefined {
  const entry = prefetchedStories.get(storyId);
  if (!entry) return undefined;
  if (entry.expiresAt <= (options.now || Date.now)()) {
    prefetchedStories.delete(storyId);
    return undefined;
  }
  return entry.promise;
}
