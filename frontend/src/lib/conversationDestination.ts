export function conversationDestination(summary: { id: string; kind: "chat" | "debate"; source?: Record<string, any> }): string {
  if (summary.kind === "debate" || summary.source?.type === "debate") return `/finance/debate?conversationId=${encodeURIComponent(summary.id)}`;
  const source = summary.source || {};
  const params = new URLSearchParams({ conversationId: summary.id });
  for (const key of ["type", "code", "panel", "eventId", "date"]) if (source[key]) params.set(key === "type" ? "source" : key, String(source[key]));
  if (source.type === "stock" && /^\d{6}$/.test(source.code || "")) return `/finance/stocks/${source.code}/ai?${params}`;
  return `/finance/ai?${params}`;
}
