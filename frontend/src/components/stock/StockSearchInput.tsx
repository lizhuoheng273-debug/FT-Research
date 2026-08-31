import { useEffect, useId, useRef } from "react";
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
  const skipSyncRef = useRef(false);
  const listId = useId();
  const search = useStockSearch(value);

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
      if (target instanceof Node && !rootRef.current?.contains(target)) search.close();
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [search]);

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
        className={cn("rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-100", className)}
      />

      {search.open && (
        <div id={listId} role="listbox" className="absolute left-0 top-full z-30 mt-1 w-full min-w-64 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
          {search.loading && <p className="px-3 py-2 text-xs text-slate-500">搜索中…</p>}
          {!search.loading && search.error && <p className="px-3 py-2 text-xs text-rose-600">{search.error}</p>}
          {!search.loading && !search.error && search.results.length === 0 && <p className="px-3 py-2 text-xs text-slate-500">暂无匹配股票</p>}
          {!search.loading && !search.error && search.results.map((result, index) => (
            <button
              key={result.code}
              id={`${listId}-${index}`}
              type="button"
              role="option"
              aria-selected={index === search.highlightedIndex}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => selectResult(result)}
              className={cn("flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm text-slate-900 hover:bg-slate-50", index === search.highlightedIndex && "bg-slate-100")}
            >
              <span className="min-w-0 truncate">{result.name}</span>
              <span className="shrink-0 text-xs text-slate-500"><span className="font-mono">{result.code}</span><span className="ml-2">A股</span></span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
