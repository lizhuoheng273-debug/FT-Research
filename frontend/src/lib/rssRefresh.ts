import type { RssSource } from "@/lib/rssSubscriptions";

export interface RssRefreshResult {
  source: RssSource;
  outcome: "updated" | "current" | "cached";
  addedCount: number;
  retryAfter?: number;
}

type RefreshRequest = (source: RssSource, signal: AbortSignal) => Promise<RssRefreshResult>;
type ActiveRefresh = { controller: AbortController; serial: number; promise: Promise<void> };

/** Coordinates manual RSS refreshes without coupling card state to networking. */
export function createRssRefresher(request: RefreshRequest, onResult: (result: RssRefreshResult) => void) {
  const active = new Map<string, ActiveRefresh>();
  let serial = 0;
  let disposed = false;

  const refresh = (source: RssSource): Promise<void> => {
    const existing = active.get(source.id);
    if (existing) return existing.promise;
    if (disposed) return Promise.resolve();
    const controller = new AbortController();
    const currentSerial = ++serial;
    const promise = (async () => {
      try {
        const result = await request(source, controller.signal);
        if (!disposed && active.get(source.id)?.serial === currentSerial) onResult(result);
      } finally {
        if (active.get(source.id)?.serial === currentSerial) active.delete(source.id);
      }
    })();
    active.set(source.id, { controller, serial: currentSerial, promise });
    return promise;
  };

  return {
    refresh,
    isRefreshing: (id: string) => active.has(id),
    invalidate: (sourceIds: string[]) => {
      for (const sourceId of sourceIds) {
        active.get(sourceId)?.controller.abort();
        active.delete(sourceId);
      }
    },
    dispose: () => {
      disposed = true;
      for (const entry of active.values()) entry.controller.abort();
      active.clear();
    },
  };
}
