import { CalendarDays, ExternalLink } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import type { FinancialCalendarResponse, FinancialHotRankItem, FinancialNewsSourceStatus } from "@/lib/api";

function safeHref(url?: string | null) {
  return url && /^https?:\/\//i.test(url) ? url : undefined;
}
function safePlacementHref(item: FinancialHotRankItem["placements"][number]) {
  const roots: Record<string,string> = {ths:"10jqka.com.cn",eastmoney:"eastmoney.com",cls:"cls.cn",sina:"sina.com.cn"};
  try {
    const url = new URL(item.originalUrl);
    const root = roots[item.sourceId];
    return root && (url.hostname === root || url.hostname.endsWith(`.${root}`)) && /^https?:$/.test(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}
function timestamp(value?: string | null, timeOnly = false) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "时间未提供";
  return new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai", ...(timeOnly ? {} : {month:"2-digit",day:"2-digit"}),hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(value));
}
function LoadingRows() {
  return <div role="status" aria-label="正在读取资讯" className="space-y-4 py-5">{[1,2,3].map(i => <div key={i} className="h-8 animate-pulse rounded-lg bg-muted/50 motion-reduce:animate-none" />)}</div>;
}

function HotRankRows({items,onOpenStory}: {items: FinancialHotRankItem[];onOpenStory?: (item: FinancialHotRankItem)=>void}) {
  return <ol className="divide-y divide-border">
    {items.map((item,index)=><li key={item.id} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 py-3.5">
      <span className={`mt-0.5 flex h-6 w-6 items-center justify-center rounded text-xs font-bold ${(item.rank || index+1)<=3?"bg-primary text-primary-foreground":"bg-muted text-muted-foreground"}`}>{item.rank || index+1}</span>
      <div className="min-w-0">
        <button type="button" data-news-title="true" onClick={()=>onOpenStory?.(item)} className="text-left text-sm font-medium leading-6 hover:text-primary focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">{item.title}</button>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{item.platformCount} 个平台上榜</span>
          {item.placements.map(placement=><a key={`${item.id}-${placement.sourceId}`} href={safePlacementHref(placement)} target="_blank" rel="noopener noreferrer" className="hover:text-primary" onClick={event=>event.stopPropagation()}>{placement.sourceName} #{placement.sourceRank} · {placement.listKind==="popularity"?"热门榜":"编辑精选"}</a>)}
          {item.stale&&<span className="text-warning">缓存</span>}
        </div>
      </div>
    </li>)}
  </ol>;
}

export function GlobalHotList({ items, loading, error, generatedAt, sourceStatus = [], onOpenStory }: {items: FinancialHotRankItem[]; loading: boolean; error?: string | null; generatedAt?: string | null; sourceStatus?: FinancialNewsSourceStatus[]; onOpenStory?: (item: FinancialHotRankItem)=>void}) {
  const unavailable = sourceStatus.filter(source => source.ok === false);
  return <GlassCard glow>
    <div className="mb-3 flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">GLOBAL FINANCE / HOT TOPICS</p><h2 className="mt-1 text-lg font-semibold">全球财经热点榜</h2><p className="mt-1 text-xs text-muted-foreground">数据更新：{generatedAt ? timestamp(generatedAt,true) : "等待首次更新"}</p></div><span className="shrink-0 font-mono text-xs">Top 10</span></div>
    {error && <p role="alert" className="py-2 text-sm text-warning">{error}{items.length ? "，保留上次结果。" : ""}</p>}
    {loading && !items.length ? <LoadingRows /> : !items.length ? <p className="py-8 text-center text-sm">暂无可用的平台热点榜。</p> : <>
      <HotRankRows items={items.slice(0,5)} onOpenStory={onOpenStory}/>
      {items.length>5&&<details className="group border-t border-border/40"><summary className="cursor-pointer list-none py-3 text-center text-sm text-primary focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"><span className="group-open:hidden">展开第 6–10 条</span><span className="hidden group-open:inline">收起第 6–10 条</span></summary><HotRankRows items={items.slice(5,10)} onOpenStory={onOpenStory}/></details>}
    </>}
    {sourceStatus.length>0 && <details className="mt-3 border-t border-border/40 pt-3 text-xs"><summary className={`cursor-pointer ${unavailable.length ? "text-warning" : "text-muted-foreground"}`}>信源状态：{sourceStatus.length-unavailable.length}/{sourceStatus.length} 可用</summary><ul className="mt-2 space-y-1 text-muted-foreground">{sourceStatus.map(source=><li key={source.id || source.source || source.name}>{source.name || source.source}：{source.ok === false ? source.error || "本次更新失败，使用最近缓存" : `已更新 ${source.count ?? 0} 条`}</li>)}</ul></details>}
  </GlassCard>;
}

export function UpcomingEvents({data,loading,error}: {data: FinancialCalendarResponse | null;loading:boolean;error?:string|null}) {
  const groups = new Map<string, FinancialCalendarResponse["items"]>();
  for (const item of data?.items || []) groups.set(item.date, [...(groups.get(item.date) || []), item]);
  const unavailable = (data?.sources || []).filter(s=>!s.ok);
  return <GlassCard>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 className="flex items-center gap-2 text-lg font-semibold"><CalendarDays className="h-5 w-5 text-primary" />未来重要事件</h2><span className="text-xs">未来 14 天 · 已确认时间转为北京时间</span></div>
    {error && <p role="alert" className="mb-3 text-sm text-warning">{error}</p>}
    {data?.stale && <p className="mb-3 text-sm text-warning">部分日程为缓存，请以官方最新安排为准。</p>}
    {loading && !data ? <LoadingRows /> : !groups.size ? <p className="py-8 text-center text-sm">{data?.partial ? "日程来源暂不完整，目前没有可展示的已确认事件。" : "未来 14 天暂无已确认的重要事件。"}</p> :
      <div className="divide-y divide-border/40">{[...groups].map(([day,items])=><section key={day} className="grid gap-2 py-4 sm:grid-cols-[6rem_minmax(0,1fr)] sm:gap-4" aria-label={day}>
        <h3 className="font-mono text-sm font-semibold text-primary">{day.slice(5).replace("-","月")}日</h3>
        <ul className="space-y-4">{items.map(item=><li key={item.id} className="grid grid-cols-[5rem_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1">
          <span className="font-mono text-xs">{item.startsAt ? timestamp(item.startsAt,true) : "时间待定"}</span>
          <a href={safeHref(item.originalUrl)} target="_blank" rel="noopener noreferrer" className="text-sm font-medium leading-6 hover:text-primary focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">{item.title}<ExternalLink className="ml-1 inline h-3 w-3" /></a>
          <div className="col-start-2 flex flex-wrap gap-x-3 gap-y-1 text-xs"><span className="text-primary">{item.category}</span><span>{item.source}</span>{!item.startsAt && <span>日期为当地日期（{item.sourceTimezone}）</span>}{item.stale && <span className="text-warning">缓存 · {timestamp(item.fetchedAt)}</span>}</div>
        </li>)}</ul>
      </section>)}</div>}
    {unavailable.length>0 && <details className="mt-3 border-t border-border/40 pt-3 text-xs"><summary className="cursor-pointer text-warning">{unavailable.length} 个日程来源暂不可用，可能有遗漏</summary><ul className="mt-2 space-y-1">{unavailable.map(s=><li key={s.id}>{s.name}：{s.error || "等待刷新"}</li>)}</ul></details>}
  </GlassCard>;
}
