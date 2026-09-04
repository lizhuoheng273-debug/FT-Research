import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { BarChart3, Building2, CalendarClock, Loader2, MessageSquare, Sparkles, Wallet } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { EarningsSnapshot } from "@/components/ui/EarningsSnapshot";
import { GlassCard } from "@/components/ui/GlassCard";
import {
  api, type Announcement, type BlockTradeRow, type Blocks, type CompanyProfile,
  type DividendRow, type DragonTiger, type Financials, type FundFlowRow,
  type HolderRow, type HotConcept, type Lockup, type MarginRow, type NewsItem,
  type QaRow, type Report, type ValMetric, type ValPercentile, type Valuation,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type PanelKey = "news" | "funds" | "company" | "finance" | "events";
type NewsKind = "news" | "announcements" | "reports";

const PANELS: { key: PanelKey; label: string }[] = [
  { key: "news", label: "资讯" },
  { key: "funds", label: "资金筹码" },
  { key: "company", label: "公司简况" },
  { key: "finance", label: "财务估值" },
  { key: "events", label: "事件互动" },
];

interface PanelData {
  news?: NewsItem[]; announcements?: Announcement[]; reports?: Report[];
  margin?: MarginRow[]; fundFlow?: FundFlowRow[]; holders?: HolderRow[];
  blockTrades?: BlockTradeRow[]; dragonTiger?: DragonTiger | null;
  profile?: CompanyProfile | null; blocks?: Blocks | null; hotConcepts?: HotConcept[];
  valuation?: Valuation | null; financials?: Financials | null; percentile?: ValPercentile | null;
  dividends?: DividendRow[]; lockup?: Lockup | null; qa?: QaRow[];
}

const fmt = (value: number | string | null | undefined, suffix = "") => value === null || value === undefined || value === "" ? "—" : `${value}${suffix}`;
const yi = (value: number) => `${(value / 1e8).toFixed(2)} 亿`;
const percent = (value: number | null | undefined) => value == null || !Number.isFinite(Number(value)) ? "—" : `${Number(value).toFixed(2)}%`;

function Empty({ children = "暂无可用数据" }: { children?: string }) {
  return <div className="rounded-xl border border-dashed border-border/70 px-4 py-10 text-center text-sm text-muted-foreground">{children}</div>;
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="rounded-xl bg-muted/30 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-mono text-base font-bold">{value}</p>{note && <p className="mt-0.5 text-[11px] text-muted-foreground">{note}</p>}</div>;
}

function ListRow({ date, meta, title, href }: { date?: string; meta?: string; title: string; href?: string }) {
  return <div className="grid gap-1 border-b border-border/40 py-3 text-sm last:border-0 sm:grid-cols-[7rem_1fr_auto] sm:items-center">
    <span className="font-mono text-xs text-muted-foreground">{date || "—"}</span>
    {href ? <a href={href} target="_blank" rel="noreferrer" className="min-w-0 hover:text-primary">{title}</a> : <span>{title}</span>}
    {meta && <span className="text-xs text-muted-foreground">{meta}</span>}
  </div>;
}

function ValBand({ label, metric }: { label: string; metric: ValMetric }) {
  const zone = metric.percentile < 20 ? "低估区" : metric.percentile > 80 ? "高估区" : "合理区";
  const tone = metric.percentile < 20 ? "text-success" : metric.percentile > 80 ? "text-danger" : "text-muted-foreground";
  return <div className="space-y-2">
    <div className="flex items-center justify-between gap-3 text-sm"><b>{label}</b><span className="text-muted-foreground">当前 {metric.current} · <span className={tone}>{metric.percentile}% {zone}</span></span></div>
    <div className="relative h-2 overflow-hidden rounded-full bg-gradient-to-r from-success/35 via-muted to-danger/35"><span className="absolute top-1/2 h-4 w-0.5 -translate-y-1/2 bg-foreground" style={{ left: `${Math.min(100, Math.max(0, metric.percentile))}%` }} /></div>
  </div>;
}

function NewsPanel({ data, kind, onKind }: { data: PanelData; kind: NewsKind; onKind: (kind: NewsKind) => void }) {
  const kinds: { key: NewsKind; label: string }[] = [{ key: "news", label: "新闻" }, { key: "announcements", label: "公告" }, { key: "reports", label: "研报" }];
  return <>
    <div className="mb-4 flex gap-2">{kinds.map((item) => <button key={item.key} onClick={() => onKind(item.key)} className={cn("rounded-lg px-4 py-2 text-sm", kind === item.key ? "bg-primary text-primary-foreground" : "bg-muted/40 text-muted-foreground hover:text-foreground")}>{item.label}</button>)}</div>
    <GlassCard>
      {kind === "news" && ((data.news?.length || 0) > 0 ? data.news!.slice(0, 20).map((item, index) => <ListRow key={index} date={(item.发布时间 || "").slice(0, 16)} meta={item.文章来源} title={item.新闻标题 || "未命名新闻"} href={item.新闻链接} />) : <Empty>暂无个股新闻</Empty>)}
      {kind === "announcements" && ((data.announcements?.length || 0) > 0 ? data.announcements!.slice(0, 20).map((item, index) => <ListRow key={index} date={item.date} meta={item.type} title={item.title.replace(/^[^:：]*[:：]/, "")} href={item.url} />) : <Empty>暂无近期公告</Empty>)}
      {kind === "reports" && ((data.reports?.length || 0) > 0 ? data.reports!.slice(0, 20).map((item, index) => <ListRow key={index} date={(item.publishDate || "").slice(0, 10)} meta={item.orgSName} title={item.title} href={item.pdfUrl || undefined} />) : <Empty>暂无近期研报</Empty>)}
    </GlassCard>
  </>;
}

function FundsPanel({ data }: { data: PanelData }) {
  const latestMargin = data.margin?.[0];
  const latestHolder = data.holders?.[0];
  const flow = (data.fundFlow || []).slice(-20).reduce((sum, item) => sum + item.main_net, 0);
  return <div className="space-y-4">
    <GlassCard><h3 className="mb-3 flex items-center gap-2 font-semibold"><Wallet className="h-4 w-4 text-primary" />资金与筹码概览</h3><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Metric label="融资余额" value={latestMargin ? yi(latestMargin.rzye) : "—"} note={latestMargin?.date} />
      <Metric label="融券余额" value={latestMargin ? yi(latestMargin.rqye) : "—"} />
      <Metric label="股东户数" value={latestHolder ? Number(latestHolder.holder_num).toLocaleString() : "—"} note={latestHolder ? `环比 ${percent(latestHolder.change_ratio)}` : undefined} />
      <Metric label="近20日主力净流入" value={data.fundFlow?.length ? yi(flow) : "—"} />
    </div></GlassCard>
    <GlassCard><h3 className="mb-3 font-semibold">近期大宗交易</h3>{data.blockTrades?.length ? data.blockTrades.slice(0, 8).map((item, index) => <ListRow key={index} date={item.date} meta={`折溢 ${item.premium_pct}%`} title={`${item.price} 元 · 买 ${item.buyer} · 卖 ${item.seller}`} />) : <Empty />}</GlassCard>
    <GlassCard><h3 className="mb-3 font-semibold">龙虎榜</h3>{data.dragonTiger?.records?.length ? data.dragonTiger.records.slice(0, 8).map((item, index) => <ListRow key={index} date={item.date} meta={`净买 ${item.net_buy} 万`} title={item.reason} />) : <Empty>近30日暂无龙虎榜记录</Empty>}</GlassCard>
  </div>;
}

function CompanyPanel({ data }: { data: PanelData }) {
  const profile = data.profile;
  if (!profile) return <Empty>公司资料暂不可用</Empty>;
  const fields = [
    ["公司全称", profile.fullName], ["英文名称", profile.englishName], ["所属市场", profile.market], ["所属行业", profile.industry],
    ["法定代表人", profile.legalRepresentative], ["注册资本", profile.registeredCapitalWan == null ? "" : `${profile.registeredCapitalWan.toLocaleString()} 万元`],
    ["成立日期", profile.establishedDate], ["上市日期", profile.listedDate], ["联系电话", profile.phone], ["电子邮箱", profile.email],
    ["注册地址", profile.registeredAddress], ["办公地址", profile.officeAddress],
  ];
  return <div className="space-y-4">
    <GlassCard glow><div className="mb-4 flex flex-wrap items-center gap-2"><Building2 className="h-5 w-5 text-primary" /><h3 className="font-semibold">公司资料</h3><span className="ml-auto text-xs text-muted-foreground">来源：{profile.source}{profile.partial ? " · 部分资料" : ""}</span></div><div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">{fields.map(([label, value]) => <div key={label} className="border-b border-border/40 pb-2"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-sm">{value || "—"}</p></div>)}</div>{profile.website && <a href={profile.website} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm text-primary hover:underline">访问公司官网</a>}</GlassCard>
    <GlassCard><h3 className="mb-2 font-semibold">主营业务</h3><p className="text-sm leading-7 text-muted-foreground">{profile.mainBusiness || "暂无资料"}</p>{profile.businessScope && <details className="mt-4 border-t border-border/40 pt-3"><summary className="cursor-pointer text-sm font-medium">展开经营范围</summary><p className="mt-3 text-sm leading-7 text-muted-foreground">{profile.businessScope}</p></details>}{profile.companyHistory && <details className="mt-3 border-t border-border/40 pt-3"><summary className="cursor-pointer text-sm font-medium">展开公司沿革</summary><p className="mt-3 text-sm leading-7 text-muted-foreground">{profile.companyHistory}</p></details>}</GlassCard>
    <GlassCard><h3 className="mb-3 font-semibold">行业、板块与热门概念</h3><div className="flex flex-wrap gap-2">{[profile.industry, ...(data.blocks?.concept_tags || []), ...(data.hotConcepts || []).map((item) => item.concept)].filter(Boolean).slice(0, 30).map((label, index) => <span key={`${label}-${index}`} className="rounded-full border border-border/70 px-2.5 py-1 text-xs text-muted-foreground">{label}</span>)}</div></GlassCard>
  </div>;
}

function FinancePanel({ data }: { data: PanelData }) {
  const val = data.valuation;
  const fin = data.financials;
  const pctl = data.percentile;
  if (!val) return <Empty>财务估值数据暂不可用</Empty>;
  const metrics = [
    ["PE(TTM)", fmt(val.pe_ttm)], ["PB", fmt(val.pb)], ["总市值", fmt(val.mcap_yi, " 亿")], ["机构覆盖", fmt(val.analyst_count, " 家")],
    ["26E EPS", fmt(val.eps_26e)], ["前向 PE", fmt(val.pe_26e)], ["PEG", fmt(val.peg)], ["消化年数", fmt(val.digest_years, " 年")],
  ];
  return <div className="space-y-4">
    <GlassCard glow><h3 className="mb-3 flex items-center gap-2 font-semibold"><BarChart3 className="h-4 w-4 text-primary" />估值摘要</h3><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{metrics.map(([label, value]) => <Metric key={label} label={label} value={value} />)}</div>{val.forecast_note && <p className="mt-3 text-xs text-warning">{val.forecast_note}</p>}</GlassCard>
    <EarningsSnapshot val={val} fin={fin || null} pctl={pctl || null} />
    {fin && <GlassCard><h3 className="mb-3 font-semibold">财务关键指标{fin.period ? ` · ${fin.period}` : ""}</h3><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{([[
      "营业总收入", fin.revenue], ["归母净利润", fin.net_profit], ["每股收益", fin.eps], ["ROE", fin.roe], ["毛利率", fin.gross_margin], ["净利率", fin.net_margin], ["每股净资产", fin.bvps], ["每股经营现金流", fin.op_cf_ps],
    ] as Array<[string, string | null]>).map(([label, value]) => <Metric key={label} label={label} value={value || "—"} />)}</div></GlassCard>}
    {pctl && (pctl.metrics.pe_ttm || pctl.metrics.pb) && <GlassCard><h3 className="mb-4 font-semibold">估值历史分位 · {pctl.period}</h3><div className="space-y-5">{pctl.metrics.pe_ttm && <ValBand label="PE-TTM" metric={pctl.metrics.pe_ttm} />}{pctl.metrics.pb && <ValBand label="市净率 PB" metric={pctl.metrics.pb} />}</div></GlassCard>}
  </div>;
}

function EventsPanel({ data }: { data: PanelData }) {
  return <div className="space-y-4">
    <GlassCard><h3 className="mb-3 flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 text-primary" />分红</h3>{data.dividends?.length ? data.dividends.slice(0, 10).map((item, index) => <ListRow key={index} date={item.date} meta={`每10股派 ${item.bonus_rmb} 元`} title={item.plan} />) : <Empty />}</GlassCard>
    <GlassCard><h3 className="mb-3 flex items-center gap-2 font-semibold"><CalendarClock className="h-4 w-4 text-primary" />限售解禁</h3>{data.lockup?.upcoming?.length ? data.lockup.upcoming.map((item, index) => <ListRow key={index} date={item.date} meta={`占比 ${percent(item.ratio)}`} title={item.type} />) : <Empty>未来90天暂无待解禁记录</Empty>}</GlassCard>
    <GlassCard><h3 className="mb-3 flex items-center gap-2 font-semibold"><MessageSquare className="h-4 w-4 text-primary" />投资者互动易</h3>{data.qa?.filter((item) => item.answer).length ? data.qa.filter((item) => item.answer).slice(0, 10).map((item, index) => <div key={index} className="border-b border-border/40 py-3 text-sm last:border-0"><p className="text-muted-foreground"><b className="mr-2 text-foreground">问</b>{item.question}</p><p className="mt-2"><b className="mr-2 text-primary">答</b>{item.answer}</p><p className="mt-1 text-xs text-muted-foreground">{item.ask_time}</p></div>) : <Empty />}</GlassCard>
  </div>;
}

async function loadPanel(code: string, panel: PanelKey): Promise<PanelData> {
  if (panel === "news") {
    const [news, announcements, reports] = await Promise.all([api.news(code).catch(() => []), api.announcements(code).catch(() => []), api.reports(code).catch(() => [])]);
    return { news, announcements, reports };
  }
  if (panel === "funds") {
    const [margin, fundFlow, holders, blockTrades, dragonTiger] = await Promise.all([api.margin(code).catch(() => []), api.fundFlow(code).catch(() => []), api.holders(code).catch(() => []), api.blockTrade(code).catch(() => []), api.dragonTiger(code).catch(() => null)]);
    return { margin, fundFlow, holders, blockTrades, dragonTiger };
  }
  if (panel === "company") {
    const [profile, blocks, hotConcepts] = await Promise.all([api.companyInfo(code).catch(() => null), api.blocks(code).catch(() => null), api.hotConcepts(code).catch(() => [])]);
    return { profile, blocks, hotConcepts };
  }
  if (panel === "finance") {
    const [valuation, financials, percentile] = await Promise.all([api.valuation(code).catch(() => null), api.financials(code).catch(() => null), api.percentile(code).catch(() => null)]);
    return { valuation, financials, percentile };
  }
  const [dividends, lockup, qa] = await Promise.all([api.dividend(code).catch(() => []), api.lockup(code).catch(() => null), api.investorQa(code).catch(() => [])]);
  return { dividends, lockup, qa };
}

export function StockResearchTabs({ code, stockName }: { code: string; stockName: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedPanel = searchParams.get("panel") as PanelKey | null;
  const panel = PANELS.some((item) => item.key === requestedPanel) ? requestedPanel! : "news";
  const requestedKind = searchParams.get("subpanel") as NewsKind | null;
  const newsKind: NewsKind = ["news", "announcements", "reports"].includes(requestedKind || "") ? requestedKind! : "news";
  const cacheRef = useRef<Partial<Record<PanelKey, PanelData>>>({});
  const loadedPanels = useRef(new Set<PanelKey>());
  const inFlightRef = useRef(new Set<PanelKey>());
  const codeRef = useRef(code);
  const [version, setVersion] = useState(0);
  const [errors, setErrors] = useState<Partial<Record<PanelKey, string>>>({});
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    codeRef.current = code;
    cacheRef.current = {};
    loadedPanels.current = new Set();
    inFlightRef.current = new Set();
    setErrors({});
    setVersion((value) => value + 1);
  }, [code]);

  useEffect(() => {
    if (loadedPanels.current.has(panel) || inFlightRef.current.has(panel)) return;
    inFlightRef.current.add(panel);
    loadPanel(code, panel).then((data) => {
      if (codeRef.current !== code) return;
      cacheRef.current[panel] = data;
      loadedPanels.current.add(panel);
      setVersion((value) => value + 1);
    }).catch(() => {
      if (codeRef.current === code) setErrors((current) => ({ ...current, [panel]: "当前分类加载失败，请稍后重试" }));
    }).finally(() => inFlightRef.current.delete(panel));
  }, [code, panel, version]);

  const selectPanel = (next: PanelKey) => {
    const params = new URLSearchParams(searchParams);
    params.set("panel", next);
    if (next !== "news") params.delete("subpanel");
    setSearchParams(params, { replace: true });
  };
  const selectNewsKind = (next: NewsKind) => {
    const params = new URLSearchParams(searchParams);
    params.set("panel", "news"); params.set("subpanel", next);
    setSearchParams(params, { replace: true });
  };
  const onTabsKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const index = PANELS.findIndex((item) => item.key === panel);
    const next = (index + (event.key === "ArrowRight" ? 1 : -1) + PANELS.length) % PANELS.length;
    selectPanel(PANELS[next].key); tabRefs.current[next]?.focus();
  };

  const data = cacheRef.current[panel];
  const loading = !data && !errors[panel];
  const aiContext = data ? `股票：${stockName}（${code}）\n当前分类：${PANELS.find((item) => item.key === panel)?.label}\n客观数据：${JSON.stringify(data)}` : `股票：${stockName}（${code}），当前分类正在加载`;

  return <section className="mt-6 border-t border-border/60 pt-5">
    <div className="sticky top-0 z-20 mb-5 rounded-xl border border-border/70 bg-background/90 p-1 shadow-sm backdrop-blur-xl">
      <div role="tablist" aria-label="个股研究分类" onKeyDown={onTabsKeyDown} className="flex min-w-0 overflow-x-auto">
        {PANELS.map((item, index) => <button key={item.key} ref={(node) => { tabRefs.current[index] = node; }} role="tab" aria-selected={panel === item.key} tabIndex={panel === item.key ? 0 : -1} onClick={() => selectPanel(item.key)} className={cn("min-w-[7rem] flex-1 whitespace-nowrap rounded-lg px-4 py-2.5 text-sm font-medium transition-colors", panel === item.key ? "bg-primary text-primary-foreground shadow" : "text-muted-foreground hover:bg-muted/40 hover:text-foreground")}>{item.label}</button>)}
      </div>
    </div>
    <div className="mb-4 flex items-center justify-between gap-3"><div><h2 className="text-lg font-bold">{PANELS.find((item) => item.key === panel)?.label}</h2><p className="text-xs text-muted-foreground">只加载并展示当前分类，切换后保留本只股票的已加载数据。</p></div><AskAiButton context={aiContext} scopeKey={`${code}:${panel}`} analysisScope="stock" workspaceSource="stock-panel" workspaceCode={code} workspacePanel={panel} label="让 AI 读本分类" suggestions={["总结关键变化", "有哪些风险点", "给我一份验证清单"]} /></div>
    {loading && <GlassCard><div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在加载{PANELS.find((item) => item.key === panel)?.label}…</div></GlassCard>}
    {errors[panel] && <Empty>{errors[panel]}</Empty>}
    {data && panel === "news" && <NewsPanel data={data} kind={newsKind} onKind={selectNewsKind} />}
    {data && panel === "funds" && <FundsPanel data={data} />}
    {data && panel === "company" && <CompanyPanel data={data} />}
    {data && panel === "finance" && <FinancePanel data={data} />}
    {data && panel === "events" && <EventsPanel data={data} />}
    <div className="mt-5"><Disclaimer /></div>
  </section>;
}
