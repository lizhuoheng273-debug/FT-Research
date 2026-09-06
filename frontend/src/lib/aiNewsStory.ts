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

export interface Story {
  title?: string;
  digest?: string;
  [key: string]: unknown;
}

type StoryFetcher = (storyId: string, signal?: AbortSignal) => Promise<unknown>;

export interface LoadAiNewsStoryOptions {
  signal?: AbortSignal;
  fetcher?: StoryFetcher;
  retries?: number;
  retryDelayMs?: number;
}

const PREFETCH_CACHE_LIMIT = 10;
const prefetchedStories = new Map<string, Promise<Story>>();

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object";

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

export function prefetchAiNewsStory(storyId: string, options: LoadAiNewsStoryOptions = {}): Promise<Story> {
  const existing = prefetchedStories.get(storyId);
  if (existing) return existing;

  const promise = loadAiNewsStory(storyId, options);
  prefetchedStories.set(storyId, promise);
  while (prefetchedStories.size > PREFETCH_CACHE_LIMIT) {
    const oldest = prefetchedStories.keys().next().value as string | undefined;
    if (!oldest) break;
    prefetchedStories.delete(oldest);
  }
  void promise.catch(() => {
    if (prefetchedStories.get(storyId) === promise) prefetchedStories.delete(storyId);
  });
  return promise;
}

export function takePrefetchedAiNewsStory(storyId: string): Promise<Story> | undefined {
  return prefetchedStories.get(storyId);
}
