import type { StockSearchItem } from "@/lib/stock-search";

type StockSearchFn = (
  query: string,
  limit: number,
  signal: AbortSignal,
) => Promise<StockSearchItem[]>;

interface StockSearchRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export class StockSearchTimeoutError extends Error {
  constructor() {
    super("股票搜索请求超时");
    this.name = "StockSearchTimeoutError";
  }
}

export async function runStockSearch(
  search: StockSearchFn,
  query: string,
  limit: number,
  { signal, timeoutMs = 8_000 }: StockSearchRequestOptions = {},
): Promise<StockSearchItem[]> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);

  if (signal?.aborted) abortFromCaller();
  else signal?.addEventListener("abort", abortFromCaller, { once: true });

  const timeout = globalThis.setTimeout(() => {
    controller.abort(new StockSearchTimeoutError());
  }, timeoutMs);

  try {
    return await search(query, limit, controller.signal);
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
