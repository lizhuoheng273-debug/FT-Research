import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { buildFeaturedEventCard } from "@/lib/featuredEventCard";

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
  summary?: string;
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
    <div className="space-y-3">{topics.slice(0, 10).map((topic) => {
      const item = itemById.get(topic.id);
      const card = buildFeaturedEventCard(topic, item);
      return <div
        key={topic.id}
        role="link"
        tabIndex={0}
        aria-label={topic.title}
        onClick={() => onOpenStory(topic, item)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpenStory(topic, item);
          }
        }}
        className="group cursor-pointer rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <GlassCard className="border-border/50 transition-colors duration-150 group-hover:border-border">
          <div className="flex items-start gap-3">
            <span className="w-6 shrink-0 text-center font-mono text-sm font-bold text-primary">{card.rankLabel}</span>
            <div className="min-w-0 flex-1">
              <h3 className="text-[15px] font-semibold leading-snug text-foreground">{card.title}</h3>
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">{card.summary}</p>
            </div>
          </div>
        </GlassCard>
      </div>;
    })}</div></>}
  </>;
}
