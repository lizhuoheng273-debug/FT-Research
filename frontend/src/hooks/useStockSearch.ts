import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { isSearchTrigger, type StockSearchItem } from "@/lib/stock-search";

export interface UseStockSearchResult {
  query: string;
  results: StockSearchItem[];
  highlightedIndex: number;
  loading: boolean;
  error: string | null;
  open: boolean;
  setQuery(query: string): void;
  setHighlightedIndex(index: number): void;
  close(): void;
  clear(): void;
}

export function useStockSearch(initialQuery = "", limit = 8): UseStockSearchResult {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<StockSearchItem[]>([]);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const timerRef = useRef<number | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    const requestId = ++requestIdRef.current;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);

    if (!isSearchTrigger(trimmed)) {
      setResults([]);
      setHighlightedIndex(-1);
      setLoading(false);
      setError(null);
      setOpen(false);
      return undefined;
    }

    setOpen(true);
    setLoading(true);
    setError(null);
    timerRef.current = window.setTimeout(() => {
      api.stockSearch(trimmed, limit).then((rows) => {
        if (requestId !== requestIdRef.current) return;
        setResults(rows);
        setHighlightedIndex(rows.length > 0 ? 0 : -1);
        setLoading(false);
      }).catch(() => {
        if (requestId !== requestIdRef.current) return;
        setResults([]);
        setHighlightedIndex(-1);
        setLoading(false);
        setError("搜索失败，请稍后重试");
      });
    }, 250);

    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [query, limit]);

  const close = () => setOpen(false);
  const clear = () => {
    setQuery("");
    setResults([]);
    setHighlightedIndex(-1);
    setError(null);
    setOpen(false);
  };

  return {
    query,
    results,
    highlightedIndex,
    loading,
    error,
    open,
    setQuery,
    setHighlightedIndex,
    close,
    clear,
  };
}
