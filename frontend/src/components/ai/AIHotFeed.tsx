import { useMemo, useState } from "react";
import { ChevronDown, ExternalLink, Sparkles } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";

export interface HotFeedItem {
  id: string;
  title: string;
  summary?: string;
  score?: number;
  reason?: string;
  category?: string;
  publishedAt?: string;
  source?: string;
  links?: { aihot?: string; original?: string; story?: string };
}

export interface HotFeedTopic {
  rank: number;
  id: string;
  title: string;
  source?: string;
  sourceCount?: number;
  signalCount?: number;
  latestAt?: string;
  score?: number;
  reason?: string;
  links?: { aihot?: string; original?: string; story?: string };
}

interface Props {
  topics: HotFeedTopic[];
  items: HotFeedItem[];
  loading?: boolean;
  onOpenStory: (topic: HotFeedTopic, item?: HotFeedItem) => void;
  showEvents?: boolean;
}

function Skeletons() {
  return <div className="space-y-3" aria-label="正在加载热点"><div className="h-32 animate-pulse rounded-xl bg-muted/40" /><div className="h-32 animate-pulse rounded-xl bg-muted/40" /><div className="h-32 animate-pulse rounded-xl bg-muted/40" /></div>;
}

export function AIHotFeed({ topics, items, loading = false, onOpenStory, showEvents = true }: Props) {
  const [expanded, setExpanded] = useState(false);
  const itemById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const visibleTopics = topics.slice(0, expanded ? 10 : 5);

  if (loading) return <Skeletons />;
  return <>
    <GlassCard className="mb-5" glow>
      <div className="mb-3 flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">AI HOT / HOT TOPICS</p><h2 className="mt-1 text-lg font-semibold">热点榜</h2></div><span className="text-xs text-muted-foreground">{topics.length ? `Top ${topics.length}` : "暂无"}</span></div>
      <div className="divide-y divide-border/40">{visibleTopics.map((topic) => <button key={topic.id} onClick={() => onOpenStory(topic, itemById.get(topic.id))} className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:text-primary"><span className="w-6 shrink-0 text-center font-mono text-sm font-bold text-primary">{topic.rank}</span><span className="min-w-0 flex-1 truncate text-sm font-medium">{topic.title}</span><span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">{topic.source || "AI HOT"}</span><span className="shrink-0 text-xs text-muted-foreground">{topic.sourceCount ? `${topic.sourceCount} 源` : ""}</span></button>)}</div>
      {topics.length > 5 && <button onClick={() => setExpanded((value) => !value)} className="mt-3 flex w-full items-center justify-center gap-1 rounded-lg border border-border/60 py-2 text-xs text-muted-foreground hover:text-primary">{expanded ? "收起至前 5 条" : "展开全部 10 条"}<ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} /></button>}
    </GlassCard>
    {showEvents && <><div className="mb-3 flex items-baseline justify-between"><h2 className="text-lg font-semibold">精选事件</h2><span className="text-xs text-muted-foreground">共 {topics.length} 条</span></div>
    <div className="space-y-3">{topics.slice(0, 10).map((topic) => { const item = itemById.get(topic.id); const score = item?.score ?? topic.score; return <div key={topic.id} role="link" tabIndex={0} onClick={() => onOpenStory(topic, item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onOpenStory(topic, item); }} className="cursor-pointer"><GlassCard className="transition-colors hover:border-primary/40"><div className="flex gap-3"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 font-mono text-sm font-bold text-primary">{topic.rank}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="font-semibold">{topic.title}</h3><span className="font-mono text-xs text-primary">{score != null ? `热度 ${score}` : "热点"}</span></div><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{item?.summary || "点击查看事件详情与报道时间线"}</p><div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground/70"><span>{topic.source || item?.source || "AI HOT"}</span><span>{item?.publishedAt || topic.latestAt || ""}</span>{(item?.reason || topic.reason) && <span className="text-primary/80"><Sparkles className="mr-1 inline h-3 w-3" />{item?.reason || topic.reason}</span>}{item?.links?.original && <a href={item.links.original} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="hover:text-primary"><ExternalLink className="mr-1 inline h-3 w-3" />原文</a>}{topic.links?.aihot && <a href={topic.links.aihot} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="hover:text-primary">AI HOT</a>}</div></div></div></GlassCard></div>; })}</div></>}
  </>;
}
