import { useEffect, useRef } from "react";
import { RotateCcw, X } from "lucide-react";
import type { RssSource, RssTrashEntry } from "@/lib/rssSubscriptions";

interface Props {
  open: boolean;
  entries: RssTrashEntry[];
  sources: RssSource[];
  selectedIds: string[];
  onSelectedIdsChange: (ids: string[]) => void;
  onClose: () => void;
  onRestoreSelected: () => void;
  onRestoreAll: () => void;
}

export function RssTrashDialog({
  open,
  entries,
  sources,
  selectedIds,
  onSelectedIdsChange,
  onClose,
  onRestoreSelected,
  onRestoreAll,
}: Props) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const sourceNames = new Map(sources.map((source) => [source.id, source.name]));
  const selected = new Set(selectedIds);

  useEffect(() => {
    if (!open) return;
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open) return null;

  const labelFor = (entry: RssTrashEntry) => entry.custom?.name || sourceNames.get(entry.id) || entry.id;
  const toggleSelected = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    onSelectedIdsChange([...next]);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-[2px]"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="rss-trash-title"
        className="flex max-h-[min(680px,calc(100vh-2rem))] w-full max-w-xl flex-col overflow-hidden rounded-[26px] border border-border bg-card shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border/60 p-5 sm:p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">LOCAL RECOVERY</p>
            <h2 id="rss-trash-title" className="mt-1 text-xl font-semibold">回收站</h2>
            <p className="mt-1 text-sm text-muted-foreground">已移除的订阅可恢复到原来的排序位置。</p>
          </div>
          <button ref={closeButtonRef} type="button" onClick={onClose} aria-label="关闭回收站" className="rounded-full border border-border p-2 text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
          {entries.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">回收站为空。</p>
          ) : (
            <div className="space-y-2">
              {entries.map((entry) => {
                const label = labelFor(entry);
                return (
                  <label key={entry.id} className="flex items-center gap-3 rounded-xl border border-border/70 px-3 py-3 hover:bg-muted/30">
                    <input type="checkbox" checked={selected.has(entry.id)} onChange={() => toggleSelected(entry.id)} aria-label={`选择${label}`} className="h-4 w-4 accent-primary" />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{label}</span>
                    <span className="text-xs text-muted-foreground">{entry.kind === "custom" ? "自定义" : "默认"}</span>
                  </label>
                );
              })}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border/60 p-5 sm:p-6">
          <button type="button" onClick={onClose} className="h-10 rounded-full border border-border px-4 text-sm">取消</button>
          <button type="button" onClick={onRestoreSelected} disabled={selectedIds.length === 0} className="inline-flex h-10 items-center gap-1 rounded-full border border-primary/40 px-4 text-sm text-primary disabled:opacity-40">
            <RotateCcw className="h-4 w-4" />恢复所选
          </button>
          <button type="button" onClick={onRestoreAll} disabled={entries.length === 0} className="h-10 rounded-full bg-primary px-4 text-sm text-primary-foreground disabled:opacity-40">全部恢复</button>
        </div>
      </div>
    </div>
  );
}
