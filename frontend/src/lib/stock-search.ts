import type { StockSearchResult } from "@/lib/api";

export type StockSearchItem = StockSearchResult;

export interface StockSearchState {
  results: StockSearchItem[];
  loading: boolean;
  error: string | null;
}

const CJK = /[\u3400-\u9fff]/;
const ASCII_QUERY = /^[A-Za-z0-9.]+$/;
const A_STOCK_CODE = /^\d{6}$/;

export function isSearchTrigger(query: string): boolean {
  const trimmed = query.trim();
  if (!trimmed) return false;
  if (CJK.test(trimmed)) return trimmed.length >= 1;
  return ASCII_QUERY.test(trimmed) && trimmed.length >= 2;
}

export function normalizeAStockCode(value: string): string | null {
  const code = value.trim().toUpperCase();
  return A_STOCK_CODE.test(code) ? code : null;
}

export function mergeBatchCodes(existing: string[], incoming: StockSearchItem[]): StockSearchItem[] {
  const seen = new Set(existing.filter((code) => A_STOCK_CODE.test(code)));
  return incoming.filter((item) => {
    const code = normalizeAStockCode(item.code);
    if (!code || seen.has(code)) return false;
    seen.add(code);
    return true;
  }).map((item) => ({ ...item, code: normalizeAStockCode(item.code) as string }));
}
