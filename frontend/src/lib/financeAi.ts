export type FinanceAiSource = "review" | "news" | "watchlist" | "index" | "stock" | "stock-panel" | "news-story";
export type AiWorkspaceSource = FinanceAiSource | "ai-news" | "ai-daily";

export interface FinanceAiTarget {
  source: FinanceAiSource;
  code?: string;
  panel?: string;
  eventId?: string;
  date?: string;
}

export function buildFinanceAiKey(source: FinanceAiSource, identifiers: { code?: string; panel?: string; eventId?: string; date?: string } = {}): string {
  if (source === "review") return `review:${identifiers.date || "latest"}`;
  if (source === "news") return "news";
  if (source === "news-story") return `news-story:${identifiers.eventId || "unknown"}`;
  if (source === "watchlist") return "watchlist";
  if (source === "index") return `index:${identifiers.code || "unknown"}`;
  if (source === "stock") return `stock:${identifiers.code || "unknown"}`;
  return `stock-panel:${identifiers.code || "unknown"}:${identifiers.panel || "overview"}`;
}

export function buildFinanceAiPath(target: FinanceAiTarget): string {
  const params = new URLSearchParams({ source: target.source });
  if (target.code) params.set("code", target.code);
  if (target.panel) params.set("panel", target.panel);
  if (target.eventId) params.set("eventId", target.eventId);
  if (target.date) params.set("date", target.date);
  return `/finance/ai?${params.toString()}`;
}

export function buildAiWorkspacePath(source: AiWorkspaceSource, identifiers: Omit<FinanceAiTarget, "source"> = {}): string {
  if (source === "ai-news" || source === "ai-daily") {
    const params = new URLSearchParams({ source });
    if (identifiers.date) params.set("date", identifiers.date);
    return `/ai/conversations?${params.toString()}`;
  }
  return buildFinanceAiPath({ source, ...identifiers });
}
