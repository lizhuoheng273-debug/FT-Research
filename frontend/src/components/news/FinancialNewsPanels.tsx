import { CalendarDays, ExternalLink } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import type { FinancialCalendarResponse, FinancialNewsItem } from "@/lib/api";

function safeHref(url?: string | null) {
  return url && /^https?:\/\//i.test(url) ? url : undefined;
}
function timestamp(value?: string | null, timeOnly = false) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "时间未提供";
  return new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai", ...(timeOnly ? {} : {month:"2-digit",day:"2-digit"}),hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(value));
}
function LoadingRows() {
  return <div role="status" aria-label="正在读取资讯" className="space-y-4 py-5">{[1,2,3].map(i => <div key={i} className="h-8 animate-pulse rounded-lg bg-muted/50 motion-reduce:animate-none" />)}</div>;
}

export function GlobalHotList({ items, loading, error }: {items: FinancialNewsItem[]; loading: boolean; error?: string | null}) {
  return <GlassCard glow>
    <div className="mb-3 flex items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">GLOBAL FINANCE / HOT TOPICS</p><h2 className="mt-1 text-lg font-semibold">全球财经热点榜</h2></div><span className="shrink-0 font-mono text-xs">Top 5</span></div>
    {error && <p role="alert" className="py-2 text-sm text-warning">{error}{items.length ? "，保留上次结果。" : ""}</p>}
    {loading && !items.length ? <LoadingRows /> : !items.length ? <p className="py-8 text-center text-sm">暂无符合多来源确认条件的财经热点，不以单一报道凑数。</p> :
      <ol className="divide-y divide-border/40">{items.slice(0,5).map((item,index) => <li key={item.id} className="grid grid-cols-[1.5rem_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1 py-3.5 sm:grid-cols-[1.5rem_minmax(0,1fr)_auto]">
        <span className="text-center font-mono text-sm font-bold text-primary">{index+1}</span>
        <a data-news-title="true" href={safeHref(item.originalUrl)} target="_blank" rel="noopener noreferrer" className="min-w-0 text-sm font-medium leading-6 hover:text-primary focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">{item.displayTitle || item.title}</a>
        <time className="col-start-2 text-xs sm:col-start-3 sm:text-right" dateTime={item.latestAt || item.publishedAt || undefined}>{timestamp(item.latestAt || item.publishedAt)}</time>
        <div className="col-start-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs sm:col-span-2">
          <span>{item.independentSourceCount || 0} 个独立来源</span>
          <span className="text-primary">{(item.independentSources || item.relatedSources || [item.source]).filter(Boolean).slice(0,4).join(" · ")}</span>
          {item.stale && <span className="text-warning">缓存</span>}
        </div>
      </li>)}</ol>}
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
