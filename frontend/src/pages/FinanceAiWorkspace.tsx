import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Bot, Database, RefreshCw, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AiConversation, TOOL_LABEL } from "@/components/ai/AiConversation";
import { GlassCard } from "@/components/ui/GlassCard";
import { useAiChatSession } from "@/hooks/useAiChatSession";
import { api, type AiStatus, type FinancialCalendarResponse, type FinancialNewsItem, type FinancialNewsOverview, type MarketReview, type Quote } from "@/lib/api";
import { buildFinanceAiKey, type FinanceAiSource } from "@/lib/financeAi";
import { loadWatch } from "@/lib/watchlist";
import { cn } from "@/lib/utils";

const SOURCES: FinanceAiSource[] = ["review", "news", "watchlist", "index", "stock", "stock-panel", "news-story"];
const suggestions: Record<FinanceAiSource, string[]> = {
  review: ["今天盘面最重要的矛盾是什么", "指数和宽度是否背离", "列出明天需要验证的信号"],
  news: ["今天最重要的三条资讯是什么", "这些资讯如何影响 A 股", "哪些结论还需要核实"],
  watchlist: ["帮我按风险分组自选股", "哪些数据最值得补充", "列出逐只验证清单"],
  index: ["这段指数走势如何", "成交量和波动有什么信息", "列出需要验证的因素"],
  stock: ["先帮我建立这只股票的研究框架", "当前估值需要重点验证什么", "列出可能证伪投资逻辑的风险"],
  "stock-panel": ["总结当前分类的关键变化", "有哪些风险点", "给我一份验证清单"],
  "news-story": ["这件事为什么重要", "按时间梳理相关报道", "涉及哪些行业和公司"],
};

function parseSource(value: string | null): FinanceAiSource {
  return SOURCES.includes(value as FinanceAiSource) ? value as FinanceAiSource : "news";
}

function scopeFor(source: FinanceAiSource): "market" | "index" | "sector" | "stock" | "general" {
  if (source === "review") return "market";
  if (source === "index") return "index";
  if (source === "stock" || source === "stock-panel") return "stock";
  return "general";
}

function safeText(value: unknown, limit = 3600): string {
  const text = typeof value === "string" ? value : String(value ?? "数据缺失");
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function formatQuote(quote: Quote | undefined, code: string): string {
  return quote ? `${quote.name}（${code}）：现价 ${quote.price}，涨跌 ${quote.change_pct > 0 ? "+" : ""}${quote.change_pct}%；PE(TTM) ${quote.pe_ttm ?? "缺失"}；换手 ${quote.turnover_pct ?? "缺失"}%` : `${code}：行情暂不可用`;
}

function buildContext(source: FinanceAiSource, payload: unknown, code: string, panel: string, eventId: string): string {
  if (source === "review") {
    const review = payload as MarketReview | null;
    return review ? [`来源：每日复盘快照`, `交易日：${review.tradingDate}`, `指数：${review.indices.slice(0, 4).map((item) => `${item.name} ${item.price}（${item.changePct ?? "缺失"}%）`).join("；")}`, `宽度：上涨 ${review.breadth.up ?? "缺失"}、下跌 ${review.breadth.down ?? "缺失"}、涨停 ${review.breadth.limitUp ?? "缺失"}、跌停 ${review.breadth.limitDown ?? "缺失"}`, `成交额：${review.liquidity.todayAmountYuan ?? "缺失"}；变化 ${review.liquidity.changePct ?? "缺失"}%`, `板块：${review.sectors.slice(0, 8).map((item) => `${item.name} ${item.net}`).join("；")}`].join("\n") : "每日复盘快照暂不可用。";
  }
  if (source === "news" ) {
    const data = payload as { overview?: FinancialNewsOverview; calendar?: FinancialCalendarResponse } | null;
    const highlights = data?.overview?.globalHighlights || [];
    const upcoming = data?.calendar?.items || [];
    return data ? [`来源：金融市场资讯`, `全球财经热点：${highlights.slice(0, 5).map((item) => `${item.displayTitle || item.title}（${item.independentSources?.join("、") || item.source} · ${item.latestAt || item.publishedAt || "日期缺失"}）`).join("；") || "暂无"}`, `未来重要事件（计划，非已发生事实）：${upcoming.map((item) => `${item.title}（${item.startsAt || item.date + ' 当地日期，时间待定'}；${item.source}；${item.originalUrl}）`).join("；") || "暂无已确认日程"}`, `日程完整性：${data.calendar?.partial ? "部分来源不可用，可能有遗漏" : "仅覆盖已接入的官方来源"}`].join("\n") : "金融资讯快照暂不可用。";
  }
  if (source === "news-story") {
    const story = payload as FinancialNewsItem | null;
    return story ? `来源：金融资讯事件\n事件：${story.title}\n摘要：${story.summary || "缺失"}\n来源：${story.source || "缺失"}\n事件编号：${eventId}` : `金融资讯事件 ${eventId} 暂不可用。`;
  }
  if (source === "index") {
    const index = payload as { name?: string; quote?: { price?: number; changePct?: number }; points?: unknown[] } | null;
    return index ? `来源：指数研究\n指数：${index.name || code}\n行情：${safeText(index.quote ? `现价 ${index.quote.price}，涨跌 ${index.quote.changePct}%` : "缺失")}\n图表样本：${index.points?.length ?? 0} 根` : `指数 ${code} 行情暂不可用。`;
  }
  if (source === "stock" || source === "stock-panel") {
    const quotes = payload as Record<string, Quote> | null;
    return `来源：${source === "stock-panel" ? `个股分类 ${panel}` : "个股研究"}\n${formatQuote(quotes?.[code], code)}\n财务、估值、新闻和研报按问题按需查询，不假设未提供数据。`;
  }
  const quotes = payload as Record<string, Quote> | null;
  const codes = Object.keys(quotes || {});
  return `来源：自选股\n${codes.length ? codes.slice(0, 30).map((item) => formatQuote(quotes?.[item], item)).join("\n") : "还没有自选股。"}`;
}

export function FinanceAiWorkspace() {
  const [params] = useSearchParams();
  const route = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const source = parseSource(params.get("source") || (route.code ? "stock" : "news"));
  const code = params.get("code") || route.code || "";
  const panel = params.get("panel") || "overview";
  const eventId = params.get("eventId") || "";
  const conversationId = params.get("conversationId") || undefined;
  const date = params.get("date") || "";
  const [payload, setPayload] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);

  const load = () => {
    setLoading(true); setError(null);
    let request: Promise<unknown>;
    if (source === "review") request = api.marketReview();
    else if (source === "news") {
      request = Promise.all([
        api.financialNewsOverview(),
        api.financialNewsCalendar(),
      ]).then(([overview, calendar]) => ({ overview, calendar }));
    }
    else if (source === "news-story") request = eventId ? api.financialNewsEvent(eventId) : Promise.reject(new Error("缺少资讯事件编号"));
    else if (source === "index") request = api.marketChart("index", code, "daily");
    else if (source === "stock" || source === "stock-panel") request = api.quote(code);
    else { const codes = loadWatch(); request = codes.length ? api.quote(codes.join(",")) : Promise.resolve({}); }
    request.then(setPayload).catch((reason) => setError(reason instanceof Error ? reason.message : "上下文暂不可用")).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [source, code, panel, eventId, date]);
  useEffect(() => { api.aiStatus().then(setAiStatus).catch(() => setAiStatus(null)); }, []);

  const context = useMemo(() => buildContext(source, payload, code, panel, eventId), [source, payload, code, panel, eventId]);
  const reviewDate = source === "review" ? ((payload as MarketReview | null)?.tradingDate || date || "latest") : date;
  const conversationKey = buildFinanceAiKey(source, { code, panel, eventId, date: reviewDate });
  const session = useAiChatSession({ conversationKey, conversationId, context, analysisScope: scopeFor(source) });
  const stateFrom = (location.state as { from?: string } | null)?.from;
  const title = source === "review" ? "每日复盘 AI" : source === "news" ? "金融资讯 AI" : source === "news-story" ? "资讯事件 AI" : source === "watchlist" ? "自选股 AI" : source === "index" ? "指数研究 AI" : source === "stock-panel" ? `${code} · ${panel} AI` : `${code} · 个股 AI`;
  const returnTo = () => { if (stateFrom) navigate(stateFrom, { replace: true }); else navigate(source === "stock" || source === "stock-panel" ? `/finance/stocks/${code}` : "/finance/news", { replace: true }); };
  const tools = useMemo(() => [...new Map(session.toolUses.map((tool) => [`${tool.name}:${tool.arg}`, tool])).values()], [session.toolUses]);

  return <div className="flex h-[calc(100dvh-1.5rem)] flex-col overflow-hidden">
    <GlassCard glow className="mb-3 shrink-0 p-4"><div className="grid grid-cols-[auto_1fr_auto] items-center gap-3"><button type="button" onClick={returnTo} className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 px-3 py-2 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /><span className="hidden sm:inline">返回</span></button><div className="min-w-0 text-center"><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">Finance AI Workspace</p><h1 className="truncate text-lg font-bold sm:text-xl">{title}</h1><p className="text-xs text-muted-foreground">来源 {source}{code ? ` · ${code}` : ""}{loading ? " · 读取上下文…" : error ? " · 数据缺失" : ""}</p></div><div className="flex items-center justify-end gap-2"><div className="hidden text-right sm:block"><p className="text-xs font-medium">{aiStatus?.model || "AI 模型"}</p><p className={cn("text-[10px]", aiStatus?.configured ? "text-success" : "text-warning")}>{aiStatus ? (aiStatus.configured ? "已连接" : "尚未配置") : "读取状态…"}</p></div>{session.messages.length > 0 && <button type="button" onClick={session.clearChat} aria-label="清空对话" title="清空对话" className="rounded-lg border border-border/70 p-2 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>}<button type="button" onClick={load} disabled={loading} aria-label="刷新上下文" title="刷新上下文" className="rounded-lg border border-border/70 p-2 text-muted-foreground hover:text-primary disabled:opacity-50"><RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /></button></div></div></GlassCard>
    <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_19rem]"><GlassCard className="flex min-h-0 min-w-0 flex-col overflow-hidden p-0"><div className="flex items-center gap-2 border-b border-border/60 px-4 py-3 text-xs text-muted-foreground"><Bot className="h-4 w-4 text-primary" /><span>流式研究对话</span><span className="ml-auto rounded-full bg-primary/10 px-2 py-0.5 text-primary">复用统一会话</span></div><AiConversation session={session} mode="workspace" placeholder="提出一个具体问题，AI 会按需调用数据…" suggestions={suggestions[source]} /></GlassCard><aside className="hidden min-h-0 overflow-auto lg:block"><div className="space-y-3"><GlassCard className="p-4"><div className="mb-3 flex items-center gap-2"><Database className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">已带入上下文</h2><span className="ml-auto text-[10px] text-muted-foreground">{error ? "缺失" : "轻量"}</span></div><pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-muted/25 p-3 font-mono text-[11px] leading-5 text-muted-foreground">{context}</pre>{error && <p className="mt-2 text-xs text-warning">{error}</p>}</GlassCard><GlassCard className="p-4"><div className="mb-3 flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">工具调用记录</h2></div>{tools.length ? <div className="space-y-2">{tools.map((tool) => <div key={`${tool.name}:${tool.arg}`} className="rounded-lg bg-muted/35 p-2.5 text-xs"><p className="font-medium">{TOOL_LABEL[tool.name] || tool.name}</p>{tool.arg && <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{tool.arg}</p>}</div>)}</div> : <p className="text-xs leading-5 text-muted-foreground">尚未调用；开始提问后显示实际查询的数据。</p>}</GlassCard><GlassCard className="border-warning/20 p-4"><p className="flex items-start gap-2 text-xs leading-5 text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-warning" />AI 输出可能存在错误，请核对原始数据，不将回答直接视为投资建议。</p></GlassCard></div></aside></div>
  </div>;
}
