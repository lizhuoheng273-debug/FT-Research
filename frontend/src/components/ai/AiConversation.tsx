import { memo, useEffect, useRef } from "react";
import { AlertCircle, Loader2, Send, Square, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SaveNoteButton } from "@/components/ui/SaveNoteButton";
import type { AiChatSession } from "@/hooks/useAiChatSession";
import { cn } from "@/lib/utils";
import { canSaveAnswer, shouldFollowOutput } from "@/lib/conversationPresentation";

const AssistantMarkdown = memo(function AssistantMarkdown({ content }: { content: string }) {
  return <div className="prose prose-sm dark:prose-invert max-w-none break-words text-foreground"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div>;
});

export const TOOL_LABEL: Record<string, string> = {
  query_quote: "查行情",
  query_valuation: "查估值",
  query_reports: "查研报",
  query_news: "查新闻",
};

export function AiConversation({ session, suggestions = [], mode = "compact", placeholder = "就本页内容提问…" }: {
  session: AiChatSession;
  suggestions?: string[];
  mode?: "compact" | "workspace";
  placeholder?: string;
}) {
  const { messages: msgs, input, setInput, loading, error, progress, send, stop } = session;
  const scrollRef = useRef<HTMLDivElement>(null);
  const followOutput = useRef(true);
  const workspace = mode === "workspace";

  useEffect(() => {
    if (followOutput.current && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [msgs, loading]);

  useEffect(() => { followOutput.current = true; }, [session.conversationId]);

  return <div className="flex min-h-0 flex-1 flex-col">
    <div ref={scrollRef} onScroll={(event) => { followOutput.current = shouldFollowOutput(event.currentTarget); }} className={cn("flex-1 overflow-auto", workspace ? "space-y-5 px-4 py-6 sm:px-8" : "space-y-3 p-4 text-sm")}>
      {msgs.length === 0 && <div className={cn("mx-auto max-w-2xl rounded-2xl border border-warning/25 bg-warning/5 text-muted-foreground", workspace ? "p-5 text-sm leading-7" : "p-3 text-xs")}>
        AI 会先阅读当前股票与实时行情，需要估值、新闻或研报时再按需调取数据。模型输出仅供研究参考，<b className="text-foreground">不构成投资建议</b>。
      </div>}
      {msgs.map((m, i) => <div key={i} className={cn("mx-auto flex w-full", workspace ? "max-w-4xl" : "", m.role === "user" ? "justify-end" : "justify-start")}>
        <div className={cn(
          "rounded-2xl leading-relaxed",
          workspace ? "max-w-[92%] px-5 py-4 text-[15px] sm:max-w-[85%]" : "max-w-[85%] px-3 py-2",
          m.role === "user" ? "bg-primary/20 text-foreground" : "bg-muted/40 text-foreground",
        )}>
          {m.tools && m.tools.length > 0 && <div className="mb-2 flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-muted-foreground/70">数据来源</span>
            {m.tools.map((tool, index) => <span key={`${tool.name}-${index}`} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary"><Wrench className="h-2.5 w-2.5" />{TOOL_LABEL[tool.name] || tool.name}{tool.arg ? ` ${tool.arg}` : ""}</span>)}
          </div>}
          {m.role === "assistant" ? <AssistantMarkdown content={m.content} /> : <p className="whitespace-pre-wrap break-words">{m.content}</p>}
          {canSaveAnswer(m) && <div className="mt-2"><SaveNoteButton kind="问AI" title={`问 AI · ${msgs[i - 1]?.content?.slice(0, 24) || "对话"}`} content={m.content} /></div>}
        </div>
      </div>)}
      {error && <div className="mx-auto flex max-w-4xl items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive"><AlertCircle className="h-3.5 w-3.5 shrink-0" />{error}</div>}
      {msgs.length === 0 && suggestions.length > 0 && <div className="mx-auto flex max-w-2xl flex-wrap justify-center gap-2 pt-1">{suggestions.map((suggestion) => <button key={suggestion} onClick={() => void send(suggestion)} className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs hover:border-primary/40 hover:text-primary">{suggestion}</button>)}</div>}
    </div>

    <div className={cn("border-t border-border/60 bg-background/70 backdrop-blur-xl", workspace ? "p-3 sm:p-5" : "p-3")}>
      {loading && <div className="mx-auto mb-3 max-w-4xl rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-sm text-foreground">
        <div role="status" aria-live="polite" className="flex items-center gap-2"><Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" /><span>{progress?.message || "请求已接收，正在分析…"}</span></div>
        <p className="mt-1 pl-6 text-xs text-muted-foreground">{typeof progress?.elapsedMs === 'number' ? `本阶段 ${Math.floor(progress.elapsedMs / 1000)} 秒 · ` : ''}正在处理，可随时停止{(progress?.elapsedMs || 0) >= 15000 ? '；当前阶段耗时较长，无需重复发送' : ''}</p>
      </div>}
      <div className={cn("mx-auto flex items-end gap-2", workspace && "max-w-4xl rounded-2xl border border-border/70 bg-input p-2 shadow-lg focus-within:border-primary/40")}>
        <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(input); } }} rows={workspace ? 2 : 1} placeholder={placeholder} className={cn("flex-1 resize-none bg-input px-3 py-2 text-sm text-input-foreground outline-none placeholder:text-input-placeholder", !workspace && "rounded-lg border border-border focus:border-primary/50")} />
        {loading ? <button onClick={() => stop()} className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-destructive/40 px-3 py-2 text-xs text-destructive hover:bg-destructive/10" aria-label="停止生成"><Square className="h-3.5 w-3.5 fill-current" />{workspace && "停止生成"}</button> : <button onClick={() => void send(input)} disabled={!input.trim()} aria-label="发送消息" className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-primary/15 px-3 py-2 text-sm text-primary hover:bg-primary/25 disabled:opacity-40"><Send className="h-4 w-4" />{workspace && "发送"}</button>}
      </div>
      {workspace && <p className="mx-auto mt-2 max-w-4xl text-center text-[11px] text-muted-foreground/60">Enter 发送 · Shift + Enter 换行 · 生成过程中可随时停止</p>}
    </div>
  </div>;
}
