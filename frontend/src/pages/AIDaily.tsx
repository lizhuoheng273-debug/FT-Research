import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BookOpen, ChevronDown } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { apiUrl, authHeaders } from "@/lib/api";

type Kind = "daily" | "weekly" | "monthly";
type Links = { aihot?: string; original?: string };
type Story = { title: string; summary?: string; publishedAt?: string; source?: { name?: string }; links?: Links };
type Section = { label: string; summary?: string; items?: Story[] };
type Edition = { period: string; periodStart?: string; leadTitle?: string; headline?: string; links?: Links };
type HeadlineImage = {url: string; alt?: string; width?: number; height?: number; layout?: "banner" | "inline"; aspectRatio?: number};
type Report = {
  date?: string; week?: string; month?: string; periodStart?: string; periodEnd?: string;
  lead?: { title?: string; leadParagraph?: string }; headline?: string; overview?: string;
  sections?: Section[]; flashes?: Story[]; highlights?: Story[]; links?: Links; attribution?: { name?: string; url?: string };
};

const LABELS: Record<Kind, string> = { daily: "日报", weekly: "周报", monthly: "月报" };
const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];
const safe = (value?: string) => {
  try {
    const url = new URL(value || "");
    return ["https:", "http:"].includes(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
};

async function request<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(apiUrl(path), { headers: authHeaders(), signal });
  if (!response.ok) throw new Error(response.status === 404 ? "该期暂无报告" : "报告暂不可用");
  return response.json() as Promise<T>;
}

function dateText(day?: string, withYear = false) {
  const match = day?.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/);
  return match ? `${withYear ? match[1] + " 年 " : ""}${Number(match[2])} 月${match[3] ? ` ${Number(match[3])} 日` : ""}` : day || "";
}

function editionPeriod(report: Report, kind: Kind, period: string) {
  if (kind === "daily") return dateText(report.date || period, true);
  if (kind === "monthly") return dateText(report.month || period, true);
  return report.periodStart && report.periodEnd
    ? `${dateText(report.periodStart, true)} — ${dateText(report.periodEnd)}` : period;
}

function Archive({ entries, kind, active, choose, compact = false }: { entries: Edition[]; kind: Kind; active: string; choose: (period: string) => void; compact?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const groups = useMemo(() => {
    const result = new Map<string, Edition[]>();
    for (const row of entries) {
      const start = row.periodStart || row.period;
      const label = kind === "monthly" ? `${start.slice(0, 4)} 年` : dateText(start.slice(0, 7), true);
      result.set(label, [...(result.get(label) || []), row]);
    }
    return [...result];
  }, [entries, kind]);
  return <aside className="edition-archive min-w-0">
      {!compact && <div className="px-2 py-3 text-sm font-semibold">往期</div>}
      {compact && <button type="button" aria-expanded={expanded} aria-controls="edition-archive-entries" onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between border-b border-[var(--edition-line)] px-2 py-2 text-sm font-semibold">
        往期 <ChevronDown className={`h-4 w-4 ${expanded ? "rotate-180" : ""}`} />
      </button>}
      <div id={compact ? "edition-archive-entries" : undefined} hidden={compact && !expanded}
        className="edition-archive-entries max-h-36 overflow-y-auto pt-2">
        {groups.map(([label, items], index) => <details key={label} open={index === 0 || items.some(item => item.period === active)} className="mb-1">
          <summary className="flex cursor-pointer list-none justify-between rounded-md px-2 py-2 text-xs text-[var(--edition-muted)]"><span>{label}</span><span>{items.length}</span></summary>
          <div className="space-y-0.5">{items.map(item => <button type="button" key={item.period} onClick={() => { choose(item.period); setExpanded(false); }} title={item.leadTitle || item.headline || item.period}
            aria-current={item.period === active ? "date" : undefined}
            className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[var(--edition-tint)] ${item.period === active ? "bg-[var(--edition-tint)] text-[var(--edition-accent)]" : ""}`}>
            <span className="w-6 shrink-0 text-center font-mono text-base font-semibold">{item.period.slice(-2)}</span>
            {kind === "daily" && <span className="shrink-0 text-xs text-[var(--edition-muted)]">周{WEEKDAYS[new Date(`${item.period}T12:00:00Z`).getUTCDay()]}</span>}
            <span className="min-w-0 truncate text-xs">{item.leadTitle || item.headline || item.period}</span>
          </button>)}</div>
        </details>)}
      </div>
  </aside>;
}

function StoryTitle({ story }: { story: Story }) {
  const href = safe(story.links?.aihot) || safe(story.links?.original);
  return href ? <a href={href} rel="noreferrer" target="_blank" className="hover:text-[var(--edition-accent)]">{story.title}</a> : <>{story.title}</>;
}

function Origin({ story }: { story: Story }) {
  const href = safe(story.links?.original);
  return href ? <a href={href} rel="noreferrer" target="_blank" className="mt-3 inline-flex items-center gap-0.5 text-xs font-medium text-[var(--edition-accent)] hover:underline">原文 <ArrowUpRight className="h-3 w-3" /></a> : null;
}

function HeadlinePicture({ image, onError }: { image: HeadlineImage; onError: () => void }) {
  const url = safe(image.url);
  if (!url) return null;
  return <figure className="edition-headline-picture m-0 overflow-hidden rounded-lg bg-[var(--edition-surface)]"
    style={{ aspectRatio: image.aspectRatio ?? (image.width && image.height ? image.width / image.height : 16 / 9) }}>
    <a href={url} target="_blank" rel="noreferrer" aria-label="查看头条原图" className="block h-full w-full focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary">
      <img src={url} alt={image.alt || ""} width={image.width} height={image.height}
        referrerPolicy="no-referrer" decoding="async" className="block h-full w-full object-cover" onError={onError} />
    </a>
  </figure>;
}

function EditionArticle({ report, kind, period }: { report: Report; kind: Kind; period: string }) {
  const [image, setImage] = useState<HeadlineImage>();
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let checks = 0;
    const load = () => {
      void request<{image?: HeadlineImage; pending?: boolean}>(`/ai/reports/editions/${kind}/${encodeURIComponent(period)}/headline-image`, controller.signal)
        .then(payload => {
          if (controller.signal.aborted) return;
          if (payload.image) setImage(payload.image);
          else if (payload.pending && ++checks < 12) timer = window.setTimeout(load, 1000);
        }).catch(() => undefined);
    };
    load();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [kind, period]);
  const sections = (report.sections || []).filter(section => section.items?.length);
  const stories = sections.flatMap(section => section.items || []);
  const flashes = report.flashes || [];
  const headline = report.headline || report.lead?.title;
  const leadStory = [...stories, ...(report.highlights || [])].find(story => story.title === headline);
  const picks = (report.highlights || stories).filter(story => story.title !== headline).slice(0, 3);
  const periodLabel = editionPeriod(report, kind, period);
  const dayNumber = kind === "weekly" ? period.slice(-2) : (kind === "daily" ? report.date || period : report.month || period).slice(-2);
  const weekDay = kind === "daily" ? WEEKDAYS[new Date(`${report.date || period}T12:00:00Z`).getUTCDay()] : undefined;
  const canonical = safe(report.links?.aihot || report.attribution?.url);
  const inlineCover = image?.layout === "inline" || (image?.layout == null && Boolean(image?.width && image.height && image.width / image.height < 1.2));
  const cover = image ? <HeadlinePicture image={image} onError={() => setImage(undefined)} /> : null;
  return <article className="edition-report min-w-0">
    <header className="edition-masthead">
      <p className="text-xs text-[var(--edition-muted)]">{periodLabel}{weekDay ? ` · 星期${weekDay}` : ""}</p>
      <div className="edition-masthead-content flex items-center justify-between gap-4 py-5">
        <div>
          <h1 className="edition-masthead-title text-3xl font-black tracking-tight">AI {LABELS[kind]}</h1>
          {canonical && <a href={canonical} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--edition-muted)] hover:text-[var(--edition-accent)]">{report.attribution?.name || "AIHOT"} 原刊 <ArrowUpRight className="h-3 w-3" /></a>}
        </div>
        <div className="flex shrink-0 items-baseline gap-1 border-l border-[var(--edition-line)] pl-2 font-mono text-[var(--edition-accent)] sm:pl-6"><span className="text-3xl font-semibold leading-none sm:text-7xl">{dayNumber}</span><span className="text-xs">{kind === "weekly" ? "周" : kind === "monthly" ? "月" : "日"}</span></div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-y border-[var(--edition-line)] py-3 text-xs text-[var(--edition-muted)]"><BookOpen className="h-3.5 w-3.5" /><span>{stories.length} 件大事</span>{flashes.length > 0 && <span>· {flashes.length} 条快讯</span>}</div>
    </header>
    {report.overview && <section className="mt-4 border-l-2 border-[var(--edition-accent)] bg-[var(--edition-tint)] px-4 py-3"><h2 className="text-xs font-bold text-[var(--edition-accent)]">本期导读</h2><p className="mt-1 text-sm leading-7">{report.overview}</p></section>}
    <section className="edition-feature border-b border-[var(--edition-line)]">
      <div className="edition-headline-column min-w-0 py-7">
        {headline && <>
          <p className="text-xs font-bold tracking-wide text-[var(--edition-accent)]">头条</p>
          <div className="edition-headline-top mt-3 flex min-w-0 flex-col gap-4">
            <h2 className="edition-headline-title break-words font-black">{leadStory ? <StoryTitle story={leadStory} /> : headline}</h2>
            {!inlineCover && cover}
          </div>
          <div className={inlineCover && cover ? "edition-headline-split mt-4 grid items-start gap-4" : "mt-3"}>
            {(report.lead?.leadParagraph || leadStory?.summary) &&
              <p className="min-w-0 break-words text-[15px] leading-[1.85]">{report.lead?.leadParagraph || leadStory?.summary}</p>}
            {inlineCover && cover}
          </div>
          {leadStory && <Origin story={leadStory} />}
        </>}
      </div>
      <aside className="edition-picks min-w-0 border-t border-[var(--edition-line)] py-7">
        {picks.length > 0 && <><h2 className="font-semibold">{kind === "daily" ? "今日看点" : kind === "weekly" ? "本周看点" : "本月看点"}</h2>
          <ol className="mt-1 divide-y divide-[var(--edition-line)]">{picks.map((story, i) => <li key={`${i}:${story.title}`} className="flex items-baseline gap-2 py-2 text-sm"><span className="font-mono text-[var(--edition-accent)]">{i + 1}</span><StoryTitle story={story} /></li>)}</ol></>}
        {(sections.length > 0 || flashes.length > 0) && <><h2 className="mt-4 font-semibold">本期版面</h2><ol className="mt-1 text-sm">
          {sections.map((section, i) => <li key={i}><a href={`#report-section-${i}`} className="flex gap-2 py-1.5 hover:text-[var(--edition-accent)]"><span className="font-mono text-[var(--edition-accent)]">{String(i + 1).padStart(2, "0")}</span><span className="flex-1">{section.label}</span><span className="text-[var(--edition-muted)]">{section.items?.length} 件</span></a></li>)}
          {flashes.length > 0 && <li><a href="#report-flashes" className="flex justify-between py-1.5 hover:text-[var(--edition-accent)]"><span>快讯</span><span className="text-[var(--edition-muted)]">{flashes.length} 条</span></a></li>}
        </ol></>}
      </aside>
    </section>
    {sections.map((section, i) => <section id={`report-section-${i}`} key={`${i}:${section.label}`} className="edition-section scroll-mt-4">
      <h2 className="edition-section-title flex items-baseline gap-3 border-b border-[var(--edition-line)] pb-3 font-black"><span className="font-mono text-[var(--edition-accent)]">{String(i + 1).padStart(2, "0")}</span>{section.label}</h2>
      {section.summary && <p className="mt-3 bg-[var(--edition-tint)] px-3 py-2 text-sm leading-6">{section.summary}</p>}
      <div className="edition-section-stories grid">{section.items?.map((story, j) => <article key={`${j}:${story.title}`} className="edition-story min-w-0 border-b border-[var(--edition-line)] py-6">
        {story.source?.name && <p className="truncate text-xs text-[var(--edition-muted)]">{story.source.name}</p>}
        <h3 className="mt-2 break-words font-bold leading-normal"><StoryTitle story={story} /></h3>
        {story.summary && <p className="mt-2 break-words text-[15px] leading-[1.85]">{story.summary}</p>}
        <Origin story={story} />
      </article>)}</div>
    </section>)}
    {flashes.length > 0 && <section id="report-flashes" className="edition-section scroll-mt-4"><h2 className="edition-section-title border-b border-[var(--edition-line)] pb-3 font-black">快讯</h2>
      <ul className="divide-y divide-[var(--edition-line)]">{flashes.map((story, i) => <li key={i} className="flex items-baseline gap-3 py-2.5 text-sm"><span className="font-mono text-xs text-[var(--edition-accent)]">{String(i + 1).padStart(2, "0")}</span><StoryTitle story={story} /></li>)}</ul>
    </section>}
  </article>;
}

export function AIDaily() {
  const [params, setParams] = useSearchParams();
  const paramKind = params.get("kind");
  const kind: Kind = paramKind === "weekly" || paramKind === "monthly" ? paramKind : "daily";
  const requested = params.get("period") || "latest";
  const [archive, setArchive] = useState<{ kind: Kind; entries: Edition[] }>();
  const [edition, setEdition] = useState<{ key: string; report: Report; period: string }>();
  const [error, setError] = useState<{ key: string; text: string }>();
  const key = `${kind}:${requested}`;
  useEffect(() => {
    const controller = new AbortController();
    void request<{ items: Edition[] }>(`/ai/reports/editions/${kind}`, controller.signal)
      .then(payload => { if (!controller.signal.aborted) setArchive({ kind, entries: payload.items }); })
      .catch(() => undefined);
    return () => controller.abort();
  }, [kind]);
  useEffect(() => {
    const controller = new AbortController();
    void request<{ period: string; report: Report }>(`/ai/reports/editions/${kind}/${encodeURIComponent(requested)}`, controller.signal)
      .then(payload => { if (!controller.signal.aborted) setEdition({ key, ...payload }); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError({ key, text: reason.message }); });
    return () => controller.abort();
  }, [kind, requested, key]);
  const active = edition?.key === key ? edition : undefined;
  const currentArchive = archive?.kind === kind ? archive.entries : [];
  function choose(value: Kind, period?: string) {
    setParams(period ? { kind: value, period } : { kind: value });
    document.querySelector("main")?.scrollTo(0, 0);
  }
  return <div className="ai-report-paper">
    <div className="edition-archive-rail">
      <nav aria-label="报告周期" className="mb-3"><PeriodButtons kind={kind} choose={choose} /></nav>
      <Archive entries={currentArchive} kind={kind} active={active?.period || requested} choose={period => choose(kind, period)} />
    </div>
    <div className="edition-reading-area min-w-0">
      <div className="edition-reading-inner">
        <div className="edition-reading-archive mb-4">
          <nav aria-label="报告周期" className="mb-4"><PeriodButtons kind={kind} choose={choose} /></nav>
          <Archive compact entries={currentArchive} kind={kind} active={active?.period || requested} choose={period => choose(kind, period)} />
        </div>
        {active ? <EditionArticle key={`${kind}:${active.period}`} report={active.report} kind={kind} period={active.period} /> : <p role="status" className="py-6 text-sm">{error?.key === key ? error.text : "加载中…"}</p>}
      </div>
    </div>
  </div>;
}

function PeriodButtons({ kind, choose }: { kind: Kind; choose: (value: Kind) => void }) {
  return <div className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-[var(--edition-line)] bg-[var(--edition-surface)] p-0.5">
    {(Object.keys(LABELS) as Kind[]).map(value => <button key={value} type="button" aria-pressed={kind === value} onClick={() => choose(value)}
      className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm font-semibold hover:text-[var(--edition-accent)] sm:px-4 ${kind === value ? "bg-[var(--edition-tint)] text-[var(--edition-accent)]" : "text-[var(--edition-muted)]"}`}>{LABELS[value]}</button>)}
  </div>;
}
