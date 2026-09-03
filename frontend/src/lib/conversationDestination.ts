export function conversationDestination(summary: { id: string; kind: "chat" | "debate"; source?: Record<string, any> }): string {
  if (summary.kind === "debate" || summary.source?.type === "debate") return `/finance/debate?conversationId=${encodeURIComponent(summary.id)}`;
  if (summary.source?.type === "stock" && /^\d{6}$/.test(summary.source.code || "")) return `/finance/stocks/${summary.source.code}/ai?conversationId=${encodeURIComponent(summary.id)}`;
  return `/finance/ai?conversationId=${encodeURIComponent(summary.id)}`;
}
