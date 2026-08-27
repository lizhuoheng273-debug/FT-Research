import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { authHeaders } from "@/lib/api";

export function AIDaily() {
  const [daily, setDaily] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetch("/api/ai/dailies/latest", { headers: authHeaders() }).then((r) => r.ok ? r.json() : Promise.reject(new Error("日报暂不可用"))).then(setDaily).catch((e) => setError(e.message)); }, []);
  const content = daily?.content || daily?.summary || daily?.markdown || "AI HOT 日报将在 V2 数据同步后显示。";
  return <div><PageHeader title="AI 日报" subtitle="按日整理 AI 领域的重要事件与原始来源" />{error && <p className="mb-3 rounded-lg border border-warning/30 p-3 text-sm text-muted-foreground">{error}</p>}<GlassCard><div className="prose prose-sm max-w-none dark:prose-invert"><ReactMarkdown>{typeof content === "string" ? content : JSON.stringify(content, null, 2)}</ReactMarkdown></div></GlassCard></div>;
}
