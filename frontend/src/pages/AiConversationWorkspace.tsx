import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Bot, RefreshCw, Trash2 } from "lucide-react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { AiConversation } from "@/components/ai/AiConversation";
import { ConversationRail } from "@/components/ai/ConversationRail";
import { GlassCard } from "@/components/ui/GlassCard";
import { useAiChatSession } from "@/hooks/useAiChatSession";
import { apiUrl, authHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";

type HotTopic = { rank?: number; title?: string; source?: string };

const sourceLabel: Record<"ai-news" | "ai-daily", string> = {
  "ai-news": "AI 热点资讯",
  "ai-daily": "AI 日报",
};

function parseSource(value: string | null): "ai-news" | "ai-daily" {
  return value === "ai-daily" ? "ai-daily" : "ai-news";
}

export function AiConversationWorkspace() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const source = parseSource(params.get("source"));
  const conversationId = params.get("conversationId") || undefined;
  const date = params.get("date") || "";
  const requestVersion = useRef(0);
  const [context, setContext] = useState("正在读取 AI 板块上下文…");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    let cancelled = false;
    const version = ++requestVersion.current;
    setLoading(true);
    setError(null);
    const read = async (path: string) => {
      const response = await fetch(apiUrl(path), { headers: authHeaders() });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      return body;
    };
    const request = source === "ai-news"
      ? Promise.all([read("/ai/news/hot-topics"), read("/ai/news?mode=selected&window=24h&limit=50")]).then(([hot, feed]) => {
        const topics = ((hot.items || []) as HotTopic[]).sort((a, b) => (a.rank || 0) - (b.rank || 0)).slice(0, 10);
        const items = Array.isArray(feed.items) ? feed.items : [];
        return [`来源：AI 热点资讯`, `热点：${topics.map((item) => `${item.rank || ""}. ${item.title || "未命名热点"}（${item.source || "未知来源"}）`).join("；") || "暂无"}`, `订阅资讯：${items.slice(0, 20).map((item: { title?: string; source?: string }) => `${item.title || "未命名资讯"}（${item.source || "未知来源"}）`).join("；") || "暂无"}`].join("\n");
      })
      : Promise.resolve(`来源：AI 日报${date ? `\n日期：${date}` : ""}\n当前会话从 AI 日报入口进入，具体报告内容按问题读取。`);
    request.then((value) => { if (!cancelled && version === requestVersion.current) setContext(value); }).catch((reason) => { if (!cancelled && version === requestVersion.current) { setContext(`来源：${sourceLabel[source]}\n上下文暂不可用。`); setError(reason instanceof Error ? reason.message : "上下文暂不可用"); } }).finally(() => { if (!cancelled && version === requestVersion.current) setLoading(false); });
    return () => { cancelled = true; };
  };

  useEffect(() => load(), [source, date]);

  const conversationKey = `ai:${source}:${date || "latest"}`;
  const session = useAiChatSession({ conversationKey, conversationId, context, contextReady: !loading && !error, analysisScope: "general", source: { type: source, date } });
  const stateFrom = (location.state as { from?: string } | null)?.from;
  const returnTo = () => navigate(stateFrom || (source === "ai-daily" ? "/ai/daily" : "/ai/news"), { replace: true });
  const startNew = () => { session.clearChat(); const next = new URLSearchParams(params); next.delete("conversationId"); navigate(`/ai/conversations?${next}`); };
  const suggestions = source === "ai-news"
    ? ["今天最重要的三件事是什么", "这些热点有哪些共同趋势", "哪些信息还需要进一步核实"]
    : ["总结本期 AI 日报", "本期最值得关注的主题是什么", "列出需要继续验证的问题"];

  return <div className="flex h-[calc(100dvh-1.5rem)] flex-col overflow-hidden">
    <GlassCard glow className="mb-3 shrink-0 p-4"><div className="grid grid-cols-[auto_1fr_auto] items-center gap-3"><button type="button" onClick={returnTo} className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 px-3 py-2 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /><span className="hidden sm:inline">返回</span></button><div className="min-w-0 text-center"><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">AI CONVERSATION WORKSPACE</p><h1 className="truncate text-lg font-bold sm:text-xl">{sourceLabel[source]}</h1><p className="text-xs text-muted-foreground">来源 {source}{loading ? " · 读取上下文…" : error ? " · 数据缺失" : ""}</p></div><div className="flex items-center justify-end gap-2"><span className={cn("hidden text-[10px] sm:block", error ? "text-warning" : "text-success")}>{error ? "上下文异常" : "AI 对话"}</span>{session.messages.length > 0 && <button type="button" onClick={startNew} aria-label="清空对话" title="清空对话" className="rounded-lg border border-border/70 p-2 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>}<button type="button" onClick={load} disabled={loading} aria-label="刷新上下文" title="刷新上下文" className="rounded-lg border border-border/70 p-2 text-muted-foreground hover:text-primary disabled:opacity-50"><RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /></button></div></div></GlassCard>
    <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[15rem_minmax(0,1fr)]"><ConversationRail activeId={session.conversationId || conversationId} onNew={startNew} /><GlassCard className="flex min-h-0 min-w-0 flex-col overflow-hidden p-0"><div className="flex items-center gap-2 border-b border-border/60 px-4 py-3 text-xs text-muted-foreground"><Bot className="h-4 w-4 text-primary" /><span>AI 流式对话</span><span className="ml-auto rounded-full bg-primary/10 px-2 py-0.5 text-primary">AI 对话记录</span></div><AiConversation session={session} mode="workspace" placeholder="针对 AI 热点或日报提出一个具体问题…" suggestions={suggestions} /></GlassCard></div>
  </div>;
}
