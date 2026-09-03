import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useStockSearch } from "@/hooks/useStockSearch";
import { normalizeAStockCode, type StockSearchItem } from "@/lib/stock-search";
import { cn } from "@/lib/utils";

export interface StockSearchInputProps {
  value: string;
  onChange(value: string): void;
  onSelect(item: StockSearchItem): void;
  onSubmitCode(code: string): void;
  placeholder?: string;
  disabled?: boolean;
  allowExternalSymbols?: boolean;
  className?: string;
}

export function StockSearchInput({
  value,
  onChange,
  onSelect,
  onSubmitCode,
  placeholder = "输入股票名称或 6 位代码",
  disabled = false,
  allowExternalSymbols = false,
  className,
}: StockSearchInputProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const skipSyncRef = useRef(false);
  const listId = useId();
  const search = useStockSearch(value);
  const { open: searchOpen } = search;
  const [overlayRect, setOverlayRect] = useState<{ top: number; left: number; width: number } | null>(null);

  useEffect(() => {
    if (skipSyncRef.current) {
      skipSyncRef.current = false;
      return;
    }
    if (search.query !== value) search.setQuery(value);
  }, [search, value]);

  useEffect(() => {
    const closeOnOutsideClick = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && !rootRef.current?.contains(target) && !listRef.current?.contains(target)) search.close();
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [search]);

  useEffect(() => {
    if (!searchOpen) {
      setOverlayRect(null);
      return undefined;
    }

    const updateOverlayPosition = () => {
      const rect = rootRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(Math.max(rect.width, 256), window.innerWidth - 16);
      const left = Math.min(Math.max(rect.left, 8), window.innerWidth - width - 8);
      setOverlayRect({ top: rect.bottom + 4, left, width });
    };

    updateOverlayPosition();
    window.addEventListener("resize", updateOverlayPosition);
    window.addEventListener("scroll", updateOverlayPosition, { capture: true, passive: true });
    return () => {
      window.removeEventListener("resize", updateOverlayPosition);
      window.removeEventListener("scroll", updateOverlayPosition, { capture: true });
    };
  }, [searchOpen]);

  const selectResult = (result: StockSearchItem) => {
    skipSyncRef.current = true;
    onSelect(result);
    search.clear();
  };

  const submit = () => {
    const exactCode = normalizeAStockCode(value);
    if (exactCode) {
      onSubmitCode(exactCode);
      search.close();
      return;
    }
    if (!search.loading && search.open && search.highlightedIndex >= 0 && search.results[search.highlightedIndex]) {
      selectResult(search.results[search.highlightedIndex]);
      return;
    }
    if (allowExternalSymbols && /^[A-Za-z0-9.]+$/.test(value.trim())) {
      onSubmitCode(value.trim().toUpperCase());
      search.close();
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && search.results.length > 0) {
      event.preventDefault();
      search.setHighlightedIndex((search.highlightedIndex + 1) % search.results.length);
    } else if (event.key === "ArrowUp" && search.results.length > 0) {
      event.preventDefault();
      search.setHighlightedIndex((search.highlightedIndex - 1 + search.results.length) % search.results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      submit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      search.close();
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <input
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={search.open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={search.highlightedIndex >= 0 ? `${listId}-${search.highlightedIndex}` : undefined}
        onChange={(event) => {
          const next = event.target.value;
          skipSyncRef.current = false;
          onChange(next);
          search.setQuery(next);
        }}
        onKeyDown={onKeyDown}
        className={cn("rounded-lg border border-border bg-input px-3 py-2 text-sm text-input-foreground shadow-sm outline-none placeholder:text-input-placeholder focus:border-primary focus:ring-2 focus:ring-primary/20", className)}
      />

      {searchOpen && overlayRect && createPortal(
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          className="min-w-64 overflow-hidden rounded-lg border border-border bg-input shadow-lg"
          style={{ position: "fixed", top: overlayRect.top, left: overlayRect.left, width: overlayRect.width, zIndex: 1000 }}
        >
          {search.loading && <p className="px-3 py-2 text-xs text-muted-foreground">搜索中…</p>}
          {!search.loading && search.error && <p className="px-3 py-2 text-xs text-destructive">{search.error}</p>}
          {!search.loading && !search.error && search.results.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">暂无匹配股票</p>}
          {!search.loading && !search.error && search.results.map((result, index) => (
            <button
              key={result.code}
              id={`${listId}-${index}`}
              type="button"
              role="option"
              aria-selected={index === search.highlightedIndex}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => selectResult(result)}
              className={cn("flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm text-input-foreground hover:bg-muted/50", index === search.highlightedIndex && "bg-muted")}
            >
              <span className="min-w-0 truncate">{result.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground"><span className="font-mono">{result.code}</span><span className="ml-2">A股</span></span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}
