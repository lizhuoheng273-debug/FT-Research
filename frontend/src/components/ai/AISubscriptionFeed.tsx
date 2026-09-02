import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Check, ExternalLink, EyeOff, GripVertical, Loader2, Pin, Plus, RotateCcw, Search, Trash2, X } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { apiUrl, authHeaders } from "@/lib/api";
import { addCustomSubscription, moveSubscription, moveSubscriptionTo, orderRssSources, readRssSubscriptionState, removeCustomSource, resetSubscriptions, toggleSubscriptionFlag, writeRssSubscriptionState, type RssSource, type RssSubscriptionState } from "@/lib/rssSubscriptions";

interface Props {
  sources: RssSource[];
  loading?: boolean;
  error?: string | null;
  onSourcesChanged?: (source: RssSource) => void;
}

function sourceStatus(source: RssSource) {
  if (source.error && !source.lastSuccessAt) return { label: "不可用", className: "text-destructive" };
  if (source.stale) return { label: "已过期", className: "text-warning" };
  return { label: "健康", className: "text-success" };
}

export function AISubscriptionFeed({ sources, loading = false, error, onSourcesChanged }: Props) {
  const [subscriptionState, setSubscriptionState] = useState<RssSubscriptionState>(() => readRssSubscriptionState());
  const [query, setQuery] = useState("");
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addUrl, setAddUrl] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => { writeRssSubscriptionState(subscriptionState); }, [subscriptionState]);

  const visibleSources = useMemo(() => orderRssSources(sources, subscriptionState), [sources, subscriptionState]);
  const customIds = useMemo(() => new Set(subscriptionState.custom.map((source) => source.id)), [subscriptionState.custom]);

  const updateState = (next: RssSubscriptionState) => setSubscriptionState(next);
  const focusSource = (source: RssSource) => {
    setQuery(source.name);
    requestAnimationFrame(() => document.getElementById(`rss-source-${source.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
    setHighlightedId(source.id);
    window.setTimeout(() => setHighlightedId((current) => current === source.id ? null : current), 1800);
  };
  const move = (sourceId: string, direction: -1 | 1) => updateState(moveSubscription(subscriptionState, sourceId, direction));
  const reorder = (targetId: string) => { if (draggedId) updateState(moveSubscriptionTo(subscriptionState, draggedId, targetId)); setDraggedId(null); };

  const resolveRss = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setAdding(true); setAddError(null);
    try {
      const response = await fetch(apiUrl("/ai/rss/resolve"), { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ url: addUrl.trim() }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "RSS 地址暂不可用");
      const source = body.source as RssSource;
      updateState(addCustomSubscription(subscriptionState, { id: source.id, name: source.name, url: addUrl.trim() }));
      onSourcesChanged?.(source);
      setAddUrl(""); setShowAdd(false);
    } catch (e) { setAddError(e instanceof Error ? e.message : "RSS 地址暂不可用"); }
    finally { setAdding(false); }
  };

  const restore = () => updateState(resetSubscriptions());
  const searchMatches = query.trim() ? visibleSources.filter((source) => source.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())).slice(0, 6) : [];
  const filtered = query.trim() ? visibleSources.filter((source) => source.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) : visibleSources;

  return <section aria-labelledby="my-ai-subscriptions" className="mt-6">
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">MY AI SOURCES</p><h2 id="my-ai-subscriptions" className="mt-1 text-lg font-semibold">我的 AI 科技订阅</h2><p className="mt-1 text-xs text-muted-foreground">默认展示国内媒体；排序、置顶和隐藏仅保存在本机浏览器。</p></div><div className="flex flex-wrap items-center gap-2"><div className="relative"><label className="relative"><span className="sr-only">搜索订阅媒体</span><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索媒体" className="w-36 rounded-lg border border-border bg-background/60 py-2 pl-8 pr-2 text-sm outline-none focus:border-primary" /></label>{searchMatches.length > 0 && <div role="listbox" aria-label="匹配的订阅媒体" className="absolute right-0 z-20 mt-1 w-48 overflow-hidden rounded-lg border border-border bg-background shadow-xl">{searchMatches.map((source) => <button type="button" role="option" key={source.id} onClick={() => focusSource(source)} className="block w-full px-3 py-2 text-left text-sm hover:bg-muted/50">{source.name}</button>)}</div>}</div><button type="button" onClick={() => { setShowAdd((value) => !value); setAddError(null); }} className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"><Plus className="h-4 w-4" />添加 RSS</button><button type="button" onClick={restore} className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:text-foreground"><RotateCcw className="h-4 w-4" />恢复默认</button></div></div>
    {showAdd && <GlassCard className="mb-3"><form onSubmit={resolveRss} className="flex flex-col gap-2 sm:flex-row"><label className="sr-only" htmlFor="rss-url">RSS 或 Atom 地址</label><input id="rss-url" type="url" required value={addUrl} onChange={(event) => setAddUrl(event.target.value)} placeholder="粘贴 RSS / Atom URL" className="min-w-0 flex-1 rounded-lg border border-border bg-background/60 px-3 py-2 text-sm outline-none focus:border-primary" /><button type="submit" disabled={adding} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">{adding ? <><Loader2 className="mr-1 inline h-4 w-4 animate-spin" />验证中</> : "验证并添加"}</button><button type="button" onClick={() => setShowAdd(false)} className="rounded-lg border border-border px-4 py-2 text-sm">取消</button></form>{addError && <p className="mt-2 text-sm text-destructive">{addError}</p>}<p className="mt-2 text-xs text-muted-foreground">服务端会识别媒体名并预览最新三条；验证成功后才会保存到本机。</p></GlassCard>}
    {error && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">{error}</p>}
    {loading ? <div className="space-y-3" aria-label="正在加载媒体订阅"><div className="h-36 animate-pulse rounded-xl bg-muted/40" /><div className="h-36 animate-pulse rounded-xl bg-muted/40" /></div> : filtered.length === 0 ? <p className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground">没有匹配的订阅媒体。</p> : <div className="space-y-3">{filtered.map((source, index) => { const status = sourceStatus(source); const isCustom = customIds.has(source.id); return <article id={`rss-source-${source.id}`} key={source.id} onDragOver={(event) => event.preventDefault()} onDrop={() => reorder(source.id)} className={`transition-all ${highlightedId === source.id ? "rounded-xl ring-2 ring-primary ring-offset-2 ring-offset-background" : ""}`}><GlassCard><div className="flex items-start gap-3"><button type="button" draggable aria-label={`拖动${source.name}排序`} onDragStart={() => setDraggedId(source.id)} onPointerDown={() => setDraggedId(source.id)} onPointerUp={() => reorder(source.id)} className="mt-1 cursor-grab touch-none text-muted-foreground" title="拖动排序"><GripVertical className="h-5 w-5" /></button><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><div className="flex min-w-0 items-center gap-2"><h3 className="truncate font-semibold">{source.name}</h3>{subscriptionState.pinned.includes(source.id) && <Pin className="h-3.5 w-3.5 shrink-0 fill-current text-primary" aria-label="已置顶" />}</div><div className="flex flex-wrap items-center gap-1 text-xs"><span className={status.className}>{status.label}</span><span className="text-muted-foreground">· {source.lastSuccessAt ? new Date(source.lastSuccessAt).toLocaleString("zh-CN") : "暂无更新时间"}</span></div></div>{source.error && <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground"><AlertTriangle className="h-3.5 w-3.5" />{source.error}</p>}<div className="mt-3 divide-y divide-border/40">{source.items.slice(0, 3).map((item) => <a key={item.id} href={item.originalUrl} target="_blank" rel="noreferrer" className="block py-2 first:pt-0 last:pb-0 hover:text-primary"><div className="flex items-start justify-between gap-3"><span className="font-medium">{item.title}</span><ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" /></div>{item.summary && <p className="mt-0.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground">{item.summary}</p>}<p className="mt-1 text-xs text-muted-foreground/70">{item.publishedAt || "日期未知"}</p></a>)}</div></div><div className="flex shrink-0 items-center gap-1"><button type="button" onClick={() => move(source.id, -1)} aria-label={`上移${source.name}`} disabled={index === 0} className="rounded p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button><button type="button" onClick={() => move(source.id, 1)} aria-label={`下移${source.name}`} disabled={index === filtered.length - 1} className="rounded p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button><button type="button" onClick={() => updateState(toggleSubscriptionFlag(subscriptionState, "pinned", source.id))} aria-label={`${subscriptionState.pinned.includes(source.id) ? "取消置顶" : "置顶"}${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-primary"><Pin className="h-4 w-4" /></button>{isCustom ? <button type="button" onClick={() => updateState(removeCustomSource(subscriptionState, source.id))} aria-label={`删除${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button> : <button type="button" onClick={() => updateState(toggleSubscriptionFlag(subscriptionState, "hidden", source.id))} aria-label={`隐藏${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-destructive"><EyeOff className="h-4 w-4" /></button>}</div></div><div className="mt-2 flex justify-end"><button type="button" onClick={() => focusSource(source)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") focusSource(source); }} className="text-xs text-muted-foreground hover:text-primary">定位此媒体</button></div></GlassCard></article>; })}</div>}
    {query && filtered.length === 1 && <button type="button" onClick={() => { setQuery(""); setHighlightedId(null); }} className="mt-2 text-xs text-muted-foreground hover:text-foreground"><X className="mr-1 inline h-3 w-3" />清除搜索</button>}
    <p className="mt-3 text-xs text-muted-foreground"><Check className="mr-1 inline h-3 w-3 text-success" />拖动把手可排序；也可使用每张卡片的上移/下移按钮。</p>
  </section>;
}
