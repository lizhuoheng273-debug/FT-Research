import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { createConversationApi } from "@/lib/conversationApi";
import { conversationDestination } from "@/lib/conversationDestination";
import { useAuth } from "@/components/auth/AuthProvider";

const api = createConversationApi();

export function AiHistory() {
  const { identity } = useAuth();
  const [items, setItems] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = () => void api.list(query).then((result) => setItems(result.items)).catch((reason) => setError(reason instanceof Error ? reason.message : "历史加载失败"));
  useEffect(load, [query]);
  const label = useMemo(() => identity?.kind === "guest" ? "仅本次体验 · 游客额度由服务端控制" : "主人历史已保存到服务器", [identity?.kind]);
  return <div className="space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-bold">AI 对话记录</h1><p className="mt-1 text-sm text-muted-foreground">{label}</p></div>
      <Link to="/finance/ai" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">新对话</Link>
    </div>
    <input aria-label="搜索对话" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题" className="w-full rounded-lg border border-border bg-background px-3 py-2" />
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {!items.length ? <div className="glass rounded-xl p-10 text-center text-sm text-muted-foreground">还没有对话记录</div> : <div className="space-y-2">{items.map((item) => <div key={item.id} className="glass flex flex-wrap items-center justify-between gap-3 rounded-xl p-4">
      <Link to={conversationDestination(item)} className="min-w-0 flex-1"><div className="truncate font-medium">{item.title}</div><div className="mt-1 text-xs text-muted-foreground">{item.kind === "debate" ? "多空辩论" : "对话"} · {item.status}</div></Link>
      <div className="flex items-center gap-2 text-xs"><button onClick={() => { const title = window.prompt("新标题", item.title); if (title) void api.update(item.id, title).then(load); }} className="text-muted-foreground hover:text-foreground">改名</button><button onClick={() => { if (window.confirm("删除这段对话？")) void api.remove(item.id).then(load); }} className="text-destructive">删除</button><button onClick={() => void api.export(item.id).then((text) => { const blob = new Blob([text], { type: "text/markdown" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `${item.id}.md`; a.click(); URL.revokeObjectURL(url); })} className="text-muted-foreground hover:text-foreground">导出</button></div>
    </div>)}</div>}
  </div>;
}
