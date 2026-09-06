import type { CSSProperties, SyntheticEvent } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, ExternalLink, EyeOff, GripVertical, Loader2, Pin, RefreshCw, Trash2 } from "lucide-react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GlassCard } from "@/components/ui/GlassCard";
import type { RssSource } from "@/lib/rssSubscriptions";

interface Props {
  source: RssSource;
  index: number;
  total: number;
  isCustom: boolean;
  isRefreshing: boolean;
  isPinned: boolean;
  managing: boolean;
  selected: boolean;
  refreshMessage?: string;
  highlighted?: boolean;
  dragDisabled?: boolean;
  onSelectedChange: () => void;
  onRefresh: () => void;
  onMove: (direction: -1 | 1) => void;
  onTogglePinned: () => void;
  onRemove: () => void;
}

function sourceStatus(source: RssSource) {
  if (source.error && !source.lastSuccessAt) return { label: "暂不可用", className: "text-destructive" };
  if (source.staleReason === "fetch_failed") return { label: "更新失败 · 使用缓存", className: "text-warning" };
  if (source.staleReason === "ttl" || source.stale) return { label: "待更新", className: "text-warning" };
  return { label: "健康", className: "text-success" };
}

const stopDrag = (event: SyntheticEvent) => event.stopPropagation();

export function RssSortableCard({
  source,
  index,
  total,
  isCustom,
  isRefreshing,
  isPinned,
  managing,
  selected,
  refreshMessage,
  highlighted = false,
  dragDisabled = false,
  onSelectedChange,
  onRefresh,
  onMove,
  onTogglePinned,
  onRemove,
}: Props) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
    isSorting,
  } = useSortable({ id: source.id, disabled: dragDisabled });
  const status = sourceStatus(source);
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 1 : undefined,
  };
  const noDragProps = { "data-no-drag": true, onPointerDown: stopDrag, onKeyDown: stopDrag };

  return (
    <article
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      data-sortable-card
      data-drag-activator
      data-sortable-state={isDragging ? "dragging" : isSorting ? "sorting" : "idle"}
      aria-label={`拖动${source.name}排序`}
      aria-roledescription="可排序订阅"
      id={`rss-source-${source.id}`}
      className={`touch-pan-y transition-all ${highlighted ? "rounded-xl ring-2 ring-primary ring-offset-2 ring-offset-background" : ""}`}
    >
      <GlassCard className={isDragging ? "border-2 border-dashed border-primary/70 bg-primary/5 opacity-50" : ""}>
        <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 sm:flex">
          {managing && (
            <input
              {...noDragProps}
              type="checkbox"
              checked={selected}
              onChange={onSelectedChange}
              aria-label={`选择${source.name}`}
              className="mt-1 h-4 w-4 accent-primary"
            />
          )}
          <span className="mt-1 shrink-0 cursor-grab touch-none text-muted-foreground" aria-hidden="true" title="拖动排序">
            <GripVertical className="h-5 w-5" />
          </span>
          <div className="min-w-0 sm:flex-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <h3 className="truncate font-semibold">{source.name}</h3>
                {isPinned && <Pin className="h-3.5 w-3.5 shrink-0 fill-current text-primary" aria-label="已置顶" />}
              </div>
              <div className="flex flex-wrap items-center gap-1 text-xs">
                <span className={status.className}>{status.label}</span>
                <span className="text-muted-foreground">· {source.lastSuccessAt ? new Date(source.lastSuccessAt).toLocaleString("zh-CN") : "暂无更新时间"}</span>
              </div>
            </div>
            {refreshMessage && <p className="mt-1 text-xs text-muted-foreground">{refreshMessage}</p>}
            {source.error && <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground"><AlertTriangle className="h-3.5 w-3.5" />{source.error}</p>}
            <div {...noDragProps} className="mt-3 divide-y divide-border/40">
              {source.items.slice(0, 3).map((item) => (
                <a {...noDragProps} key={item.id} href={item.originalUrl} target="_blank" rel="noreferrer" className="block py-2 first:pt-0 last:pb-0 hover:text-primary">
                  <div className="flex items-start justify-between gap-3"><span className="font-medium">{item.title}</span><ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" /></div>
                  {item.summary && <p className="mt-0.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground">{item.summary}</p>}
                  <p className="mt-1 text-xs text-muted-foreground/70">{item.publishedAt || "日期未知"}</p>
                </a>
              ))}
              {source.items.length === 0 && <p className="py-2 text-sm text-muted-foreground">暂无缓存内容，后台刷新后会显示最新文章。</p>}
            </div>
          </div>
          <div {...noDragProps} className="col-span-2 flex flex-wrap items-center justify-end gap-1 border-t border-border/40 pt-2 sm:col-auto sm:shrink-0 sm:border-0 sm:pt-0">
            <button {...noDragProps} type="button" onClick={onRefresh} aria-label={`刷新${source.name}`} disabled={isRefreshing} className="rounded p-1.5 text-muted-foreground hover:text-primary disabled:opacity-40">
              {isRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </button>
            <button {...noDragProps} type="button" onClick={() => onMove(-1)} aria-label={`上移${source.name}`} disabled={index === 0} className="rounded p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
            <button {...noDragProps} type="button" onClick={() => onMove(1)} aria-label={`下移${source.name}`} disabled={index === total - 1} className="rounded p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button>
            <button {...noDragProps} type="button" onClick={onTogglePinned} aria-label={`${isPinned ? "取消置顶" : "置顶"}${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-primary"><Pin className="h-4 w-4" /></button>
            {isCustom ? <button {...noDragProps} type="button" onClick={onRemove} aria-label={`删除${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button> : <button {...noDragProps} type="button" onClick={onRemove} aria-label={`隐藏${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-destructive"><EyeOff className="h-4 w-4" /></button>}
          </div>
        </div>
      </GlassCard>
    </article>
  );
}

export function RssSortableCardOverlay({ source }: { source: RssSource }) {
  return (
    <div className="scale-[1.02] rounded-xl border-2 border-primary bg-card p-5 shadow-2xl">
      <p className="font-semibold">{source.name}</p>
      <p className="mt-2 truncate text-sm text-muted-foreground">{source.items[0]?.title || "正在移动此订阅"}</p>
    </div>
  );
}
