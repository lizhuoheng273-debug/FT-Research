import { useEffect, useRef, useState } from "react";
import { Download, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { conversationDestination, createConversationApi, type ConversationSummary } from "@/lib/conversationApi";
import { cn } from "@/lib/utils";

const api = createConversationApi();

export function ConversationRail({ activeId, onSelect, onNew, refreshKey = 0, sourceFamily }: {
  activeId?: string;
  onSelect?: (conversation: ConversationSummary) => void;
  onNew?: () => void;
  refreshKey?: number;
  sourceFamily?: "ai" | "finance";
}) {
  const navigate = useNavigate();
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState<"" | "ai" | "finance">(sourceFamily || "");
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const version = useRef(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setFamily(sourceFamily || ""); }, [sourceFamily]);
  useEffect(() => {
    const current = ++version.current;
    setBusy(true);
    const timer = window.setTimeout(() => {
      api.list(query, undefined, family || undefined).then(result => {
        if (current === version.current) { setItems(result.items); setCursor(result.nextCursor); setError(null); }
      }).catch(() => { if (current === version.current) setError("记录暂不可用，请重试"); })
        .finally(() => { if (current === version.current) setBusy(false); });
    }, query ? 200 : 0);
    return () => { window.clearTimeout(timer); version.current++; };
  }, [query, refreshKey, activeId, family, revision]);
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    const timer = window.setInterval(() => { if (document.visibilityState === "visible" && items.length <= 30) refresh(); }, 15000);
    window.addEventListener("focus", refresh);
    window.addEventListener("ft-conversations-changed", refresh);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", refresh); window.removeEventListener("ft-conversations-changed", refresh); };
  }, [items.length]);
  const loadMore = async () => {
    if (!cursor || busy) return;
    const current = version.current;
    setBusy(true);
    try {
      const result = await api.list(query, cursor, family || undefined);
      if (current !== version.current) return;
      setItems(items => { const seen = new Set(items.map(item => item.id)); return [...items, ...result.items.filter(item => !seen.has(item.id))]; });
      setCursor(result.nextCursor); setError(null);
    } catch { if (current === version.current) setError("加载更多失败，请重试"); }
    finally { if (current === version.current) setBusy(false); }
  };

  const select = (conversation: ConversationSummary) => {
    onSelect?.(conversation);
    navigate(conversationDestination(conversation));
  };
  const rename = async (conversation: ConversationSummary) => {
    const title = window.prompt("重命名对话", conversation.title)?.trim();
    if (!title || title === conversation.title) return;
    try {
      const updated = await api.update(conversation.id, title);
      setItems(current => current.map(item => item.id === updated.id ? updated : item));
    } catch { setError("重命名失败"); }
  };
  const remove = async (conversation: ConversationSummary) => {
    if (!window.confirm("删除这条对话记录？")) return;
    try {
      await api.remove(conversation.id);
      setItems(current => current.filter(item => item.id !== conversation.id));
      if (conversation.id === activeId) onNew?.();
    } catch { setError("删除失败"); }
  };
  const exportConversation = async (conversation: ConversationSummary) => {
    try {
      const body = await api.export(conversation.id);
      const url = URL.createObjectURL(new Blob([body], { type: "text/markdown;charset=utf-8" }));
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${conversation.title || "对话记录"}.md`; anchor.click(); URL.revokeObjectURL(url);
    } catch { setError("导出失败"); }
  };

  return <section className="flex min-h-0 flex-col rounded-2xl border border-border/60 bg-background/50 p-3 lg:h-full" aria-label="AI 对话记录">
    <div className="mb-3 flex items-center justify-between gap-2"><div><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">Conversations</p><h2 className="text-sm font-semibold">AI 对话记录</h2></div><button type="button" onClick={() => onNew?.()} className="rounded-lg border border-border/70 p-2 text-muted-foreground hover:text-primary" aria-label="新建对话" title="新建对话"><Plus className="h-4 w-4" /></button></div>
    <label className="mb-2 text-xs text-muted-foreground">记录范围<select aria-label="记录范围" value={family} onChange={event => setFamily(event.target.value as typeof family)} className="ml-2 rounded border border-border bg-input px-2 py-1 text-input-foreground"><option value="">全部</option><option value="ai">AI 板块</option><option value="finance">金融板块</option></select></label>
    <label className="mb-3 flex items-center gap-2 rounded-lg border border-border/60 bg-input px-2.5 py-2 text-xs text-muted-foreground"><Search className="h-3.5 w-3.5" /><span className="sr-only">搜索对话</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索对话" className="min-w-0 flex-1 bg-input text-input-foreground outline-none placeholder:text-input-placeholder" /></label>
    <div className="min-h-0 flex-1 space-y-1 overflow-auto pr-1">
      {items.map(conversation => <div key={conversation.id} className={cn("group rounded-xl border border-transparent p-2.5 transition-colors hover:border-border/60 hover:bg-muted/30", conversation.id === activeId && "border-primary/30 bg-primary/10")}>
        <button type="button" onClick={() => select(conversation)} className="block w-full text-left"><p className="truncate text-xs font-medium">{conversation.title}</p><p className="mt-1 truncate text-[10px] text-muted-foreground">{conversation.status === "running" ? "进行中" : new Date(conversation.updatedAt * 1000).toLocaleDateString("zh-CN")}</p></button>
        <div className="mt-2 flex items-center gap-1 opacity-70 group-hover:opacity-100"><button type="button" onClick={() => void rename(conversation)} className="rounded p-1 text-muted-foreground hover:text-foreground" aria-label={`重命名 ${conversation.title}`} title="重命名"><Pencil className="h-3 w-3" /></button><button type="button" onClick={() => void exportConversation(conversation)} className="rounded p-1 text-muted-foreground hover:text-primary" aria-label={`导出 ${conversation.title}`} title="导出"><Download className="h-3 w-3" /></button><button type="button" onClick={() => void remove(conversation)} className="rounded p-1 text-muted-foreground hover:text-destructive" aria-label={`删除 ${conversation.title}`} title="删除"><Trash2 className="h-3 w-3" /></button><MoreHorizontal className="ml-auto h-3.5 w-3.5 text-muted-foreground/40" /></div>
      </div>)}
      {busy && !items.length && <p role="status" className="p-3 text-xs text-muted-foreground">正在加载记录…</p>}
      {cursor && <button disabled={busy} onClick={() => void loadMore()} className="w-full p-2 text-xs text-primary">{busy ? "加载中…" : "加载更多"}</button>}
      {!busy && !items.length && !error && <p className="px-2 py-5 text-center text-xs text-muted-foreground">还没有对话记录</p>}
      {error && <p className="px-2 py-3 text-xs text-warning">{error}<button onClick={() => setRevision(value => value + 1)} className="ml-2 underline">重试</button></p>}
    </div>
  </section>;
}
