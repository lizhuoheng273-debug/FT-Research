import type { StockSearchItem } from "@/lib/stock-search";

type StockSearchFn = (
  query: string,
  limit: number,
  signal: AbortSignal,
) => Promise<StockSearchItem[]>;

interface StockSearchRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  retryDelayMs?: number;
}

export class StockSearchTimeoutError extends Error {
  constructor() {
    super("股票搜索请求超时");
    this.name = "StockSearchTimeoutError";
  }
}

export function stockSearchRetryDelay(error: unknown, fallbackMs: number): number {
  const retryAfterMs = (error as { retryAfterMs?: number })?.retryAfterMs;
  return Number.isFinite(retryAfterMs) && Number(retryAfterMs) > 0 ? Number(retryAfterMs) : fallbackMs;
}

export async function runStockSearch(
  search: StockSearchFn,
  query: string,
  limit: number,
  { signal, timeoutMs = 12_000, retryDelayMs = 500 }: StockSearchRequestOptions = {},
): Promise<StockSearchItem[]> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);

  if (signal?.aborted) abortFromCaller();
  else signal?.addEventListener("abort", abortFromCaller, { once: true });

  const timeout = globalThis.setTimeout(() => {
    controller.abort(new StockSearchTimeoutError());
  }, timeoutMs);

  try {
    while (true) {
      try {
        return await search(query, limit, controller.signal);
      } catch (error) {
        if ((error as { status?: number })?.status !== 503 || controller.signal.aborted) throw error;
        await new Promise<void>((resolve, reject) => {
          const onAbort = () => {
            globalThis.clearTimeout(timer);
            reject(controller.signal.reason ?? new DOMException("Aborted", "AbortError"));
          };
          const timer = globalThis.setTimeout(() => {
            controller.signal.removeEventListener("abort", onAbort);
            resolve();
          }, stockSearchRetryDelay(error, retryDelayMs));
          controller.signal.addEventListener("abort", onAbort, { once: true });
        });
      }
    }
  } catch (error) {
    if (controller.signal.aborted && controller.signal.reason) {
      throw controller.signal.reason;
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}
