import type { RssSource } from "@/lib/rssSubscriptions";

type RefreshRequest = (source: RssSource, signal: AbortSignal) => Promise<RssSource>;
type ActiveRefresh = { controller: AbortController; serial: number; promise: Promise<void> };

/** Coordinates manual RSS refreshes without coupling card state to networking. */
export function createRssRefresher(request: RefreshRequest, onSource: (source: RssSource) => void) {
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
        const refreshed = await request(source, controller.signal);
        if (!disposed && active.get(source.id)?.serial === currentSerial) onSource(refreshed);
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
    dispose: () => {
      disposed = true;
      for (const entry of active.values()) entry.controller.abort();
      active.clear();
    },
  };
}
