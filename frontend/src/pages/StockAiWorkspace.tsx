import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Bot, ChevronDown, Database, ShieldCheck, Sparkles, Trash2, X } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { AiConversation, TOOL_LABEL } from "@/components/ai/AiConversation";
import { GlassCard } from "@/components/ui/GlassCard";
import { useAiChatSession } from "@/hooks/useAiChatSession";
import { isAStockTradingTime, useLiveStockQuote } from "@/hooks/useLiveStockQuote";
import { api, type AiStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const pct = (value: number) => `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
const tone = (value: number) => value > 0 ? "text-danger" : value < 0 ? "text-success" : "text-muted-foreground";

export function StockAiWorkspace() {
  const { code: routeCode = "" } = useParams();
  const code = routeCode.replace(/[^\d]/g, "").slice(0, 6);
  const navigate = useNavigate();
  const location = useLocation();
  const { quote, error: quoteError } = useLiveStockQuote(code);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [contextOpen, setContextOpen] = useState(false);

  useEffect(() => {
    api.aiStatus().then(setAiStatus).catch(() => setAiStatus(null));
  }, []);

  useEffect(() => {
    if (!contextOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setContextOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [contextOpen]);

  const marketState = isAStockTradingTime() ? "交易中" : "非交易时段";
  const stockName = quote?.name || code;
  const context = quote
    ? `股票：${quote.name}（${code}）\n市场：A股\n实时行情：现价 ${quote.price}，昨收 ${quote.last_close}，当前涨幅 ${pct(quote.change_pct)}\n交易状态：${marketState}\n如需估值、财务、新闻或研报，请按用户问题调用相应数据工具，不要假设未提供的数据。`
    : `股票代码：${code}\n市场：A股\n实时行情暂不可用\n交易状态：${marketState}\n如需行情、估值、财务、新闻或研报，请调用相应数据工具。`;

  const session = useAiChatSession({
    conversationKey: `stock:${code}`,
    legacyConversationKey: `/finance/stocks/${code}#${code}`,
    context,
  });

  const tools = useMemo(() => {
    const seen = new Set<string>();
    return session.toolUses.filter((tool) => {
      const key = `${tool.name}:${tool.arg}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [session.toolUses]);

  const stateFrom = (location.state as { from?: string } | null)?.from;
  const fallback = `/finance/stocks/${code}`;
  const hasSourcePage = stateFrom === fallback || stateFrom?.startsWith(`${fallback}?`);
  const returnToStock = () => {
    session.stop();
    if (hasSourcePage) navigate(-1);
    else navigate(fallback, { replace: true });
  };
  const runtimeStatus = session.loading ? "正在流式生成" : session.messages.some((message) => message.role === "assistant" && !message.partial) ? "最近对话已完成" : "等待提问";

  const ContextPanel = ({ mobile = false }: { mobile?: boolean }) => <div className={cn("space-y-3", mobile && "pt-3")}>
    <GlassCard className="p-4">
      <div className="mb-3 flex items-center gap-2"><Database className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">已带入上下文</h2><span className="ml-auto rounded-full bg-success/10 px-2 py-0.5 text-[10px] text-success">轻量</span></div>
      <div className="space-y-2 text-xs text-muted-foreground">
        <p className="flex justify-between gap-3"><span>股票</span><b className="text-right text-foreground">{stockName} · {code}</b></p>
        <p className="flex justify-between gap-3"><span>实时行情</span><b className={cn("text-right", quote ? "text-foreground" : "text-warning")}>{quote ? `${quote.price.toFixed(2)} / ${pct(quote.change_pct)}` : "暂不可用"}</b></p>
        <p className="flex justify-between gap-3"><span>市场状态</span><b className="text-right text-foreground">{marketState}</b></p>
      </div>
      <p className="mt-3 border-t border-border/50 pt-3 text-[11px] leading-5 text-muted-foreground">财务、估值、新闻和研报不预加载，由 AI 根据问题按需调取，减少等待和 Token 消耗。</p>
    </GlassCard>

    <GlassCard className="p-4">
      <div className="mb-3 flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">工具调用记录</h2></div>
      {tools.length ? <div className="space-y-2">{tools.map((tool, index) => <div key={`${tool.name}-${tool.arg}-${index}`} className="rounded-lg bg-muted/35 p-2.5 text-xs"><p className="font-medium text-foreground">{TOOL_LABEL[tool.name] || tool.name}</p>{tool.arg && <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{tool.arg}</p>}</div>)}</div> : <p className="text-xs leading-5 text-muted-foreground">尚未调用。开始提问后，这里会显示 AI 实际查询的数据。</p>}
    </GlassCard>

    <GlassCard className="border-warning/20 p-4">
      <p className="flex items-start gap-2 text-xs leading-5 text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-warning" />AI 输出可能存在错误。请核对原始行情、公告和财报，不将回答直接视为投资建议。</p>
    </GlassCard>
  </div>;

  return <div className="flex h-[calc(100dvh-1.5rem)] flex-col overflow-hidden">
    <GlassCard glow className="mb-3 shrink-0 p-4">
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-3">
        <button onClick={returnToStock} className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 px-3 py-2 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /><span className="hidden sm:inline">返回个股</span></button>
        <div className="min-w-0 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">AI 个股研究</p>
          <h1 className="truncate text-lg font-bold sm:text-xl">{stockName}</h1>
          <p className="font-mono text-xs text-muted-foreground">{code} · A股</p>
          {quote ? <p className={cn("mt-1 font-mono text-sm font-bold", tone(quote.change_pct))}>{quote.price.toFixed(2)} <span className="ml-1">{pct(quote.change_pct)}</span></p> : quoteError ? <p className="mt-1 text-xs text-warning">实时行情暂不可用</p> : <p className="mt-1 text-xs text-muted-foreground">读取实时行情…</p>}
        </div>
        <div className="flex items-center justify-end gap-2">
          <div className="hidden text-right sm:block"><p className="text-xs font-medium">{aiStatus?.model || "AI 模型"}</p><p className={cn("text-[10px]", aiStatus?.configured ? "text-success" : "text-warning")}>{aiStatus ? (aiStatus.configured ? runtimeStatus : "尚未配置") : "读取状态…"}</p></div>
          {session.messages.length > 0 && <button onClick={session.clearChat} aria-label="清空对话" title="清空对话" className="rounded-lg border border-border/70 p-2 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>}
        </div>
      </div>
      <button onClick={() => setContextOpen((open) => !open)} className="mt-3 flex w-full items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-xs text-muted-foreground lg:hidden">研究上下文与工具记录<ChevronDown className={cn("h-4 w-4 transition-transform", contextOpen && "rotate-180")} /></button>
    </GlassCard>

    {contextOpen && <div className="fixed inset-0 z-50 flex items-end bg-black/55 p-3 lg:hidden" role="dialog" aria-modal="true" aria-label="研究上下文与工具记录">
      <button className="absolute inset-0" aria-label="关闭研究上下文" onClick={() => setContextOpen(false)} />
      <div className="glass relative z-10 max-h-[85dvh] w-full overflow-auto rounded-2xl p-3">
        <div className="sticky top-0 z-10 flex items-center justify-between bg-background/90 px-1 py-2 backdrop-blur-xl"><b className="text-sm">研究上下文与工具记录</b><button onClick={() => setContextOpen(false)} aria-label="关闭研究上下文" className="rounded-lg border border-border/70 p-2 text-muted-foreground"><X className="h-4 w-4" /></button></div>
        <ContextPanel mobile />
      </div>
    </div>}

    <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <GlassCard className="flex min-h-0 min-w-0 flex-col overflow-hidden p-0">
        <div className="flex items-center gap-2 border-b border-border/60 px-4 py-3 text-xs text-muted-foreground"><Bot className="h-4 w-4 text-primary" /><span>流式研究对话</span><span className="ml-auto rounded-full bg-primary/10 px-2 py-0.5 text-primary">按需调取数据</span></div>
        <AiConversation session={session} mode="workspace" placeholder={`向 AI 询问 ${stockName} 的基本面、估值、资讯或风险…`} suggestions={["先帮我建立这只股票的研究框架", "当前估值需要重点验证什么？", "梳理近期公告和新闻中的关键信号", "列出可能证伪投资逻辑的风险"]} />
      </GlassCard>
      <aside className="hidden min-h-0 overflow-auto lg:block"><ContextPanel /></aside>
    </div>
  </div>;
}
