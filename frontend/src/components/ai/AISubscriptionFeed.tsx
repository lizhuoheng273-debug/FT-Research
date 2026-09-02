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

function readableError(value?: string | null) {
  if (!value) return null;
  if (value.trim().toLowerCase() === ["not", "found"].join(" ") || /\b404\b/.test(value)) return "媒体订阅接口尚未连接，请重启本地后端后刷新。";
  return value;
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
  const [previewSource, setPreviewSource] = useState<RssSource | null>(null);

  useEffect(() => { writeRssSubscriptionState(subscriptionState); }, [subscriptionState]);
  useEffect(() => {
    if (!showAdd) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setShowAdd(false); };
    document.addEventListener("keydown", closeOnEscape);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", closeOnEscape); document.body.style.overflow = previousOverflow; };
  }, [showAdd]);

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
  const openAdd = () => { setShowAdd(true); setAddError(null); setPreviewSource(null); };
  const closeAdd = () => { if (adding) return; setShowAdd(false); setPreviewSource(null); setAddError(null); };

  const testRss = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setAdding(true); setAddError(null); setPreviewSource(null);
    try {
      const response = await fetch(apiUrl("/ai/rss/resolve"), { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ url: addUrl.trim() }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "RSS 地址暂不可用");
      setPreviewSource(body.source as RssSource);
    } catch (e) { setAddError(e instanceof Error ? e.message : "RSS 地址暂不可用"); }
    finally { setAdding(false); }
  };
  const saveRss = () => {
    if (!previewSource) return;
    updateState(addCustomSubscription(subscriptionState, { id: previewSource.id, name: previewSource.name, url: previewSource.url || addUrl.trim() }));
    onSourcesChanged?.(previewSource);
    setAddUrl(""); closeAdd();
  };

  const restore = () => updateState(resetSubscriptions());
  const searchMatches = query.trim() ? visibleSources.filter((source) => source.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())).slice(0, 6) : [];
  const filtered = query.trim() ? visibleSources.filter((source) => source.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) : visibleSources;
  const feedError = readableError(error);

  return <section aria-labelledby="my-ai-subscriptions" className="mt-6">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">MY AI SOURCES</p><h2 id="my-ai-subscriptions" className="mt-1 text-lg font-semibold">我的 AI 科技订阅</h2><p className="mt-1 text-xs text-muted-foreground">默认展示国内媒体；排序、置顶和隐藏仅保存在本机浏览器。</p></div><div className="flex flex-wrap items-center gap-2"><div className="relative"><label className="relative block"><span className="sr-only">搜索订阅媒体</span><Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索媒体" className="h-10 w-36 rounded-full border border-border bg-background/60 py-2 pl-8 pr-3 text-sm leading-none outline-none focus:border-primary" /></label>{searchMatches.length > 0 && <div role="listbox" aria-label="匹配的订阅媒体" className="absolute right-0 z-20 mt-1 w-48 overflow-hidden rounded-lg border border-border bg-background shadow-xl">{searchMatches.map((source) => <button type="button" role="option" key={source.id} onClick={() => focusSource(source)} className="block w-full px-3 py-2 text-left text-sm hover:bg-muted/50">{source.name}</button>)}</div>}</div><button type="button" onClick={openAdd} className="inline-flex h-10 items-center gap-1 rounded-full bg-primary px-4 text-sm font-medium leading-none text-primary-foreground shadow-[0_8px_20px_hsl(var(--primary)/0.2)]"><Plus className="h-4 w-4" />添加 RSS</button><button type="button" onClick={restore} className="inline-flex h-10 items-center gap-1 rounded-full border border-border px-4 text-sm leading-none text-muted-foreground hover:text-foreground"><RotateCcw className="h-4 w-4" />恢复默认</button></div></div>
    {showAdd && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.target === event.currentTarget) closeAdd(); }}><div role="dialog" aria-modal="true" aria-labelledby="add-rss-title" onKeyDown={(event) => { if (event.key === "Escape") closeAdd(); }} className="max-h-[min(760px,calc(100vh-2rem))] w-full max-w-2xl overflow-y-auto rounded-[26px] border border-border bg-card p-5 shadow-2xl sm:p-7"><div className="flex items-start justify-between gap-4"><div className="flex items-center gap-3"><span className="h-8 w-1.5 rounded-full bg-primary" /><div><h2 id="add-rss-title" className="text-xl font-semibold">添加信源</h2><p className="mt-1 text-sm text-muted-foreground">验证 RSS / Atom 地址，确认预览后保存到本机。</p></div></div><button type="button" onClick={closeAdd} aria-label="关闭添加信源" className="rounded-full border border-border p-2 text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button></div><form onSubmit={testRss} className="mt-6 space-y-4"><label className="block"><span className="mb-1.5 block text-sm font-medium">名称 <span className="text-primary">*</span></span><input value={previewSource?.name || ""} readOnly placeholder="测试连接后自动识别" className="h-11 w-full rounded-xl border border-border bg-muted/20 px-3 text-sm outline-none placeholder:text-muted-foreground/70 focus:border-primary" /></label><label className="block"><span className="mb-1.5 block text-sm font-medium">类型</span><select value="rss" disabled className="h-11 w-full appearance-none rounded-xl border border-border bg-muted/20 px-3 text-sm outline-none disabled:cursor-not-allowed disabled:opacity-100"><option value="rss">RSS（完整订阅地址）</option></select></label><label className="block"><span className="mb-1.5 block text-sm font-medium">订阅地址 <span className="text-primary">*</span></span><input id="rss-url" type="url" required value={addUrl} onChange={(event) => { setAddUrl(event.target.value); setPreviewSource(null); }} placeholder="https://example.com/feed" className="h-11 w-full rounded-xl border border-border bg-muted/20 px-3 text-sm outline-none focus:border-primary" /><span className="mt-1.5 block text-xs text-muted-foreground">填写完整 RSS/Atom 地址，服务端会自动识别媒体名称。</span></label>{previewSource && <div className="rounded-xl border border-success/30 bg-success/5 p-3"><p className="text-sm font-medium text-success">连接成功 · 最新三条预览</p><div className="mt-2 space-y-1.5">{previewSource.items.slice(0, 3).map((item) => <p key={item.id} className="truncate text-sm text-muted-foreground">{item.title}</p>)}</div></div>}{addError && <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{addError}</p>}<div className="flex flex-wrap justify-end gap-2 border-t border-border/60 pt-5"><button type="button" onClick={closeAdd} className="h-10 rounded-full border border-border px-5 text-sm">取消</button><button type="submit" disabled={adding || !addUrl.trim()} className="h-10 rounded-full border border-primary/40 px-5 text-sm text-primary hover:bg-primary/10 disabled:opacity-40">{adding ? <><Loader2 className="mr-1 inline h-4 w-4 animate-spin" />测试中</> : "测试连接"}</button><button type="button" onClick={saveRss} disabled={!previewSource || adding} className="h-10 rounded-full bg-primary px-5 text-sm text-primary-foreground disabled:opacity-40">保存并刷新</button></div></form></div></div>}
    {feedError && <p className="mb-3 rounded-xl border border-warning/40 bg-warning/5 p-3 text-sm text-muted-foreground">{feedError}</p>}
    {loading ? <div className="space-y-3" aria-label="正在加载媒体订阅"><div className="h-36 animate-pulse rounded-xl bg-muted/40" /><div className="h-36 animate-pulse rounded-xl bg-muted/40" /></div> : filtered.length === 0 ? <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground"><p>{feedError ? "暂时没有载入媒体内容。" : "没有匹配的订阅媒体。"}</p><button type="button" onClick={openAdd} className="mt-3 text-primary hover:underline">添加一个 RSS 信源</button></div> : <div className="space-y-3">{filtered.map((source, index) => { const status = sourceStatus(source); const isCustom = customIds.has(source.id); return <article id={`rss-source-${source.id}`} key={source.id} onDragOver={(event) => event.preventDefault()} onDrop={() => reorder(source.id)} className={`transition-all ${highlightedId === source.id ? "rounded-xl ring-2 ring-primary ring-offset-2 ring-offset-background" : ""}`}><GlassCard><div className="flex items-start gap-3"><button type="button" draggable aria-label={`拖动${source.name}排序`} onDragStart={() => setDraggedId(source.id)} onPointerDown={() => setDraggedId(source.id)} onPointerUp={() => reorder(source.id)} className="mt-1 cursor-grab touch-none text-muted-foreground" title="拖动排序"><GripVertical className="h-5 w-5" /></button><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><div className="flex min-w-0 items-center gap-2"><h3 className="truncate font-semibold">{source.name}</h3>{subscriptionState.pinned.includes(source.id) && <Pin className="h-3.5 w-3.5 shrink-0 fill-current text-primary" aria-label="已置顶" />}</div><div className="flex flex-wrap items-center gap-1 text-xs"><span className={status.className}>{status.label}</span><span className="text-muted-foreground">· {source.lastSuccessAt ? new Date(source.lastSuccessAt).toLocaleString("zh-CN") : "暂无更新时间"}</span></div></div>{source.error && <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground"><AlertTriangle className="h-3.5 w-3.5" />{source.error}</p>}<div className="mt-3 divide-y divide-border/40">{source.items.slice(0, 3).map((item) => <a key={item.id} href={item.originalUrl} target="_blank" rel="noreferrer" className="block py-2 first:pt-0 last:pb-0 hover:text-primary"><div className="flex items-start justify-between gap-3"><span className="font-medium">{item.title}</span><ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" /></div>{item.summary && <p className="mt-0.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground">{item.summary}</p>}<p className="mt-1 text-xs text-muted-foreground/70">{item.publishedAt || "日期未知"}</p></a>)}{source.items.length === 0 && <p className="py-2 text-sm text-muted-foreground">暂无缓存内容，后台刷新后会显示最新文章。</p>}</div></div><div className="flex shrink-0 items-center gap-1"><button type="button" onClick={() => move(source.id, -1)} aria-label={`上移${source.name}`} disabled={index === 0} className="rounded p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button><button type="button" onClick={() => move(source.id, 1)} aria-label={`下移${source.name}`} disabled={index === filtered.length - 1} className="rounded p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button><button type="button" onClick={() => updateState(toggleSubscriptionFlag(subscriptionState, "pinned", source.id))} aria-label={`${subscriptionState.pinned.includes(source.id) ? "取消置顶" : "置顶"}${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-primary"><Pin className="h-4 w-4" /></button>{isCustom ? <button type="button" onClick={() => updateState(removeCustomSource(subscriptionState, source.id))} aria-label={`删除${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button> : <button type="button" onClick={() => updateState(toggleSubscriptionFlag(subscriptionState, "hidden", source.id))} aria-label={`隐藏${source.name}`} className="rounded p-1.5 text-muted-foreground hover:text-destructive"><EyeOff className="h-4 w-4" /></button>}</div></div></GlassCard></article>; })}</div>}
    {query && filtered.length === 1 && <button type="button" onClick={() => { setQuery(""); setHighlightedId(null); }} className="mt-2 text-xs text-muted-foreground hover:text-foreground"><X className="mr-1 inline h-3 w-3" />清除搜索</button>}
    <p className="mt-3 text-xs text-muted-foreground"><Check className="mr-1 inline h-3 w-3 text-success" />拖动把手可排序；也可使用每张卡片的上移/下移按钮。</p>
  </section>;
}
