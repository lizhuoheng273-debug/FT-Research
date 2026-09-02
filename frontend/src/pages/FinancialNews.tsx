import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { GlobalHotList, UpcomingEvents } from "@/components/news/FinancialNewsPanels";
import { api } from "@/lib/api";

function useSnapshot<T>(fetcher: (signal?: AbortSignal) => Promise<T>, interval: number, revision: number) {
  const [data,setData] = useState<T|null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState<string|null>(null);
  useEffect(()=>{
    let active = true;
    let controller: AbortController | undefined;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    const load=()=>{
      controller?.abort();
      clearTimeout(deadline);
      const current = new AbortController();
      controller = current;
      setLoading(true);
      let timedOut=false;
      deadline=setTimeout(()=>{timedOut=true;current.abort();},20000);
      fetcher(current.signal).then(result=>{
        if(active && !current.signal.aborted){setData(result);setError(null);}
      }).catch(reason=>{
        if(active && controller===current && (!current.signal.aborted || timedOut)) setError(timedOut?"读取超时，请稍后刷新":reason instanceof Error?reason.message:"资讯暂不可用");
      }).finally(()=>{if(controller===current){clearTimeout(deadline);if(active)setLoading(false);}});
    };
    load();
    const timer=setInterval(()=>{if(document.visibilityState==='visible')load();},interval);
    return ()=>{active=false;clearInterval(timer);clearTimeout(deadline);controller?.abort();};
  },[fetcher,interval,revision]);
  return {data,loading,error};
}

export function FinancialNews() {
  const [revision,setRevision]=useState(0);
  const overview=useSnapshot(api.financialNewsOverview,180000,revision);
  const calendar=useSnapshot(api.financialNewsCalendar,60000,revision);
  const items=overview.data?.globalHighlights || [];
  const aiContext=useMemo(()=>JSON.stringify({source:"金融市场资讯",globalHighlights:items.slice(0,5),upcomingEvents:calendar.data?.items || [],calendarPartial:calendar.data?.partial},null,2),[items,calendar.data]);
  return <div>
    <PageHeader title="金融市场资讯" actions={<div className="flex items-center gap-2"><AskAiButton context={aiContext} workspaceSource="news" label="问 AI" suggestions={["这五条财经热点中最值得关注的是什么", "未来两周有哪些重要日程", "区分已发生事实与未来计划"]}/><button type="button" aria-label="刷新资讯" onClick={()=>setRevision(v=>v+1)} className="rounded-lg border border-border p-2 hover:text-primary"><RefreshCw className="h-4 w-4"/></button></div>}/>
    {overview.data?.stale && <p className="mb-3 text-sm text-warning">部分来源暂不可用，当前包含最近成功缓存。</p>}
    <GlobalHotList items={items} loading={overview.loading} error={overview.error}/>
    <div className="mt-5"><UpcomingEvents data={calendar.data} loading={calendar.loading} error={calendar.error}/></div>
    <Disclaimer/>
  </div>;
}
