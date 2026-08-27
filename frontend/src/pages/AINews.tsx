import { useEffect, useState } from "react";
import { ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { authHeaders } from "@/lib/api";

interface Item {
  id: string; title: string; summary?: string; score?: number; reason?: string;
  publishedAt?: string; source?: string; links?: { aihot?: string; original?: string };
}

export function AINews() {
  const [items, setItems] = useState<Item[]>([]);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setLoading(true); setError(null);
    fetch("/api/ai/news?mode=selected&window=24h&limit=50", { headers: authHeaders() })
      .then((r) => r.ok ? r.json() : r.json().then((x) => Promise.reject(new Error(x.detail || `HTTP ${r.status}`))))
      .then((x) => { setItems(x.items || []); setStale(Boolean(x.stale)); })
      .catch((e) => setError(e.message || "AI 资讯加载失败"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  const context = items.slice(0, 20).map((x, i) => `${i + 1}. ${x.title}（${x.source || "未知来源"}，${x.score ?? "—"}分）`).join("\n");
  return <div>
    <PageHeader title="AI 资讯" subtitle="热点榜优先展示，榜单外精选资讯继续向下展开" actions={<div className="flex items-center gap-2"><AskAiButton context={context || "暂无 AI 资讯"} label="AI 摘要与追问" suggestions={["今天最重要的三件事是什么？", "这些热点有哪些共同趋势？"]} /><button onClick={load} className="rounded-lg border border-border px-3 py-1.5 text-sm"><RefreshCw className="mr-1 inline h-4 w-4" />刷新</button></div>} />
    {stale && <p className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">AI HOT 暂时不可用，当前显示本地缓存。</p>}
    {error && <p className="mb-3 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
    {loading ? <p className="py-10 text-center text-sm text-muted-foreground">加载热点中…</p> : <div className="space-y-3">{items.map((item, index) => <GlassCard key={item.id}>
      <div className="flex gap-3"><div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/15 font-mono text-sm font-bold text-primary">{index + 1}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="font-semibold">{item.title}</h3><span className="font-mono text-xs text-primary">热度 {item.score ?? "—"}</span></div><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{item.summary || "暂无摘要"}</p><div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground/70"><span>{item.source || "AI HOT"}</span><span>{item.publishedAt || ""}</span>{item.reason && <span className="text-primary/80"><Sparkles className="mr-1 inline h-3 w-3" />{item.reason}</span>}{item.links?.original && <a href={item.links.original} target="_blank" rel="noreferrer" className="hover:text-primary"><ExternalLink className="mr-1 inline h-3 w-3" />原文</a>}{item.links?.aihot && <a href={item.links.aihot} target="_blank" rel="noreferrer" className="hover:text-primary">AI HOT</a>}</div></div></div>
    </GlassCard>)}</div>}
  </div>;
}
