import { Plus, X } from "lucide-react";
import { useState } from "react";
import { StockSearchInput } from "@/components/stock/StockSearchInput";
import type { StockSearchItem } from "@/lib/stock-search";

export interface StockBatchItem {
  code: string;
  name: string;
}

export interface StockBatchPickerProps {
  items: StockBatchItem[];
  onItemsChange(items: StockBatchItem[]): void;
  existingCodes: string[];
  rawValue: string;
  onRawValueChange(value: string): void;
  onPasteCodes(raw: string): void;
  placeholder?: string;
}

export function StockBatchPicker({
  items,
  onItemsChange,
  existingCodes,
  rawValue,
  onRawValueChange,
  onPasteCodes,
  placeholder = "输入股票名称，或粘贴 6 位代码（逗号 / 空格 / 换行均可）",
}: StockBatchPickerProps) {
  const [query, setQuery] = useState("");

  const addItem = (item: StockSearchItem) => {
    if (existingCodes.includes(item.code) || items.some((current) => current.code === item.code)) {
      setQuery("");
      return;
    }
    onItemsChange([...items, { code: item.code, name: item.name }]);
    setQuery("");
  };

  const addCodeItem = (code: string) => addItem({ code, name: code });

  return (
    <div className="space-y-3">
      <StockSearchInput
        value={query}
        onChange={setQuery}
        onSelect={addItem}
        onSubmitCode={addCodeItem}
        placeholder={placeholder}
      />

      {items.length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="待添加股票">
          {items.map((item) => (
            <span key={item.code} className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs text-primary">
              <span>{item.name}</span>
              <span className="font-mono text-primary/70">{item.code}</span>
              <button
                type="button"
                aria-label={`移除 ${item.name}`}
                title="移除"
                onClick={() => onItemsChange(items.filter((current) => current.code !== item.code))}
                className="rounded-full p-0.5 hover:bg-primary/15"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <textarea
          value={rawValue}
          onChange={(event) => onRawValueChange(event.target.value)}
          rows={2}
          placeholder="也可粘贴代码：600519 000858, 002463\n300750 688017"
          className="flex-1 resize-y rounded-lg border border-border bg-input px-3 py-2 text-sm text-input-foreground outline-none placeholder:text-input-placeholder focus:border-primary/50"
        />
        <button
          type="button"
          onClick={() => onPasteCodes(rawValue)}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 self-start rounded-lg bg-primary/15 px-4 text-sm font-medium text-primary shadow-glow hover:bg-primary/25"
        >
          <Plus className="h-4 w-4" /> 添加
        </button>
      </div>
    </div>
  );
}
