import { memo, useLayoutEffect, useRef } from "react";
import { AlertCircle, ArrowUp, Loader2, Sparkles, Square, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SaveNoteButton } from "@/components/ui/SaveNoteButton";
import type { AiChatSession } from "@/hooks/useAiChatSession";
import { cn } from "@/lib/utils";
import { canSaveAnswer, shouldFollowOutput } from "@/lib/conversationPresentation";
import { ReasoningControl } from "@/components/ai/ReasoningControl";

const AssistantMarkdown = memo(function AssistantMarkdown({ content }: { content: string }) {
  return <div className="prose prose-sm dark:prose-invert max-w-none break-words text-foreground"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div>;
});

export const TOOL_LABEL: Record<string, string> = {
  query_quote: "查行情",
  query_valuation: "查估值",
  query_reports: "查研报",
  query_news: "查新闻",
  query_valuation_percentile: "查历史估值分位",
  query_kline: "查 K 线",
  query_market_chart: "查量价走势",
  query_financials: "查财务指标",
  query_company_info: "查公司概况",
  query_fund_flow: "查资金流向",
  query_margin: "查融资融券",
  query_holders: "查股东户数",
  query_block_trade: "查大宗交易",
  query_dragon_tiger: "查龙虎榜",
  query_dividend: "查分红",
  query_announcements: "查公告",
  query_lockup: "查限售解禁",
  query_investor_qa: "查投资者问答",
  query_concepts: "查概念归属",
  query_industry_comparison: "对比行业板块",
  query_industry_reports: "查行业研报",
  query_market: "查大盘与市场情绪",
  query_news_radar: "查产业资讯",
  query_gpu_rent: "查 GPU 租金",
  query_global_stock: "查海外股票",
  query_hk_cashflow: "查港股现金流",
};

function activityMessage(session: AiChatSession): string {
  if (!session.loading) return "";
  // Legacy tool events may lack completion events; the current phase wins.
  const names = session.progress?.phase === "tool" ? (session.toolUses || []).filter(tool => tool.status === "running").map(tool => tool.name) : [];
  if (!names.length && session.progress?.phase === "tool" && session.progress.status === "running" && session.progress.tool) names.push(session.progress.tool);
  if (names.length) return `正在调用：${names.map(name => TOOL_LABEL[name] || name).join("、")}…`;
  return session.progress?.message || "请求已接收，正在分析…";
}

function AssistantHeader({ message = "", elapsedMs }: { message?: string; elapsedMs?: number }) {
  return <header className="mb-2 flex min-w-0 items-start gap-2.5">
    <span role="img" aria-label="AI 头像" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
      {message ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" /> : <Sparkles aria-hidden="true" className="h-3.5 w-3.5" />}
    </span>
    {message ? <div className="min-w-0 pt-1 text-xs leading-5 text-muted-foreground">
      <span role="status" aria-live="polite" className="break-words">{message}</span>
      {typeof elapsedMs === "number" && <span className="ml-1 whitespace-nowrap tabular-nums">· {Math.floor(elapsedMs / 1000)} 秒</span>}
    </div> : <span className="pt-1 text-xs leading-5 text-muted-foreground">AI</span>}
  </header>;
}

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
  const statusMessage = activityMessage(session);
  const lastMessage = msgs[msgs.length - 1];
  const activeIndex = loading && lastMessage?.role === "assistant" && !["complete", "completed", "failed", "error", "stopped", "interrupted"].includes(lastMessage.status || "") ? msgs.length - 1 : -1;

  useLayoutEffect(() => { followOutput.current = true; }, [session.conversationId]);
  const lastContent = msgs[msgs.length - 1]?.content;
  const lastStatus = msgs[msgs.length - 1]?.status;
  useLayoutEffect(() => {
    if (followOutput.current && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [session.conversationId, msgs.length, lastContent, lastStatus, error]);
  useLayoutEffect(() => {
    if (statusMessage && followOutput.current && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [statusMessage]);

  return <div className="flex min-h-0 flex-1 flex-col">
    <div ref={scrollRef} onScroll={(event) => { followOutput.current = shouldFollowOutput(event.currentTarget); }} className={cn("flex-1 overflow-auto", workspace ? "space-y-5 px-4 py-6 sm:px-8" : "space-y-3 p-4 text-sm")}>
      {msgs.length === 0 && !session.historyLoading && !loading && <div className={cn("mx-auto max-w-2xl rounded-2xl border border-warning/25 bg-warning/5 text-muted-foreground", workspace ? "p-5 text-sm leading-7" : "p-3 text-xs")}>
        AI 会先阅读当前股票与实时行情，需要估值、新闻或研报时再按需调取数据。模型输出仅供研究参考，<b className="text-foreground">不构成投资建议</b>。
      </div>}
      {msgs.map((m, i) => <div key={i} className={cn("mx-auto flex w-full", workspace ? "max-w-4xl" : "", m.role === "user" ? "justify-end" : "justify-start")}>
        <div className={cn("min-w-0", workspace ? "max-w-[92%] sm:max-w-[85%]" : "max-w-[85%]")}>
        {m.role === "assistant" && <AssistantHeader message={i === activeIndex ? statusMessage : ""} elapsedMs={i === activeIndex ? progress?.elapsedMs : undefined} />}
        {(m.content || i !== activeIndex) && <div className={cn(
          "rounded-2xl leading-relaxed",
          workspace ? "px-5 py-4 text-[15px]" : "px-3 py-2",
          m.role === "user" ? "bg-primary/20 text-foreground" : "bg-muted/40 text-foreground",
        )}>
          {m.tools && m.tools.length > 0 && <div className="mb-2 flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-muted-foreground/70">数据来源</span>
            {m.tools.map((tool, index) => <span key={`${tool.name}-${index}`} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary"><Wrench className="h-2.5 w-2.5" />{TOOL_LABEL[tool.name] || tool.name}{tool.arg ? ` ${tool.arg}` : ""}</span>)}
          </div>}
          {m.role === "assistant" ? <AssistantMarkdown content={m.content} /> : <p className="whitespace-pre-wrap break-words">{m.content}</p>}
          {m.role === "assistant" && ["failed", "error", "stopped", "interrupted"].includes(m.status || "") && <p className="mt-2 text-xs text-muted-foreground">{m.content ? "本次未完成，已保留部分回答" : "本次未生成回答，可继续提问"}</p>}
          {canSaveAnswer(m) && <div className="mt-2"><SaveNoteButton kind="问AI" title={`问 AI · ${msgs[i - 1]?.content?.slice(0, 24) || "对话"}`} content={m.content} /></div>}
        </div>}
        </div>
      </div>)}
      {loading && activeIndex < 0 && <div className={cn("mx-auto w-full", workspace && "max-w-4xl")}><AssistantHeader message={statusMessage} elapsedMs={progress?.elapsedMs} /></div>}
      {session.historyLoading && msgs.length === 0 && <p role="status" className="text-center text-sm text-muted-foreground">正在加载对话记录…</p>}
      {error && <div className="mx-auto flex max-w-4xl items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive"><AlertCircle className="h-3.5 w-3.5 shrink-0" />{error}{session.retry && <button onClick={session.retry} className="underline">重新加载</button>}</div>}
      {msgs.length === 0 && !session.historyLoading && !loading && suggestions.length > 0 && <div className="mx-auto flex max-w-2xl flex-wrap justify-center gap-2 pt-1">{suggestions.map((suggestion) => <button key={suggestion} onClick={() => void send(suggestion)} disabled={session.contextReady === false || session.historyLoading} className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs hover:border-primary/40 hover:text-primary">{suggestion}</button>)}</div>}
    </div>

    <div className={cn("bg-background", workspace ? "px-3 pb-4 pt-2 sm:px-5 sm:pb-5" : "p-3")}>
      {session.contextReady === false && !loading && <p role="status" className="mb-2 text-center text-xs text-muted-foreground">正在准备页面数据，上下文就绪后可发送</p>}
      <div className={cn("mx-auto rounded-3xl border border-border/80 bg-input p-2 text-input-foreground transition-colors focus-within:border-foreground/30", workspace && "max-w-4xl")}>
        <textarea aria-label="输入问题" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(input); } }} rows={2} placeholder={placeholder} className="block min-h-16 w-full resize-none bg-transparent px-3 pb-2 pt-3 text-sm leading-6 text-input-foreground outline-none placeholder:text-input-placeholder" />
        <div className="flex min-h-10 items-center justify-between gap-3 px-1 pt-1">
          {session.setReasoningEffort ? <ReasoningControl key={session.conversationId || "draft"} value={session.reasoningEffort || "max"} onChange={session.setReasoningEffort} disabled={session.reasoningLocked} loading={loading} /> : <span />}
          {loading ? <button type="button" onClick={() => stop()} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 focus-visible:ring-offset-2 focus-visible:ring-offset-input" aria-label="停止生成" title="停止生成"><Square aria-hidden="true" className="h-3.5 w-3.5 fill-current" /></button> : <button type="button" onClick={() => void send(input)} disabled={!input.trim() || session.contextReady === false || session.historyLoading || Boolean(error)} aria-label="发送消息" title="发送消息（Enter）" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 focus-visible:ring-offset-2 focus-visible:ring-offset-input disabled:cursor-not-allowed disabled:opacity-25"><ArrowUp aria-hidden="true" className="h-[18px] w-[18px]" /></button>}
        </div>
      </div>
    </div>
  </div>;
}
