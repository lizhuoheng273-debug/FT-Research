import { ApiError, apiUrl } from "@/lib/api";
import { authHeaders } from "@/lib/authClient";
export { conversationDestination } from "@/lib/conversationDestination";

export type ConversationSummary = { id: string; kind: "chat" | "debate"; title: string; source: Record<string, any>; updatedAt: number; status: string };
export type ConversationDetail = { conversation: ConversationSummary; messages: Array<Record<string, any>>; activeRunId: string | null };

async function jsonRequest<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const headers: Record<string, string> = { ...authHeaders(method) };
  const init: RequestInit = { method, credentials: "include", headers };
  if (body !== undefined) { headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
  const response = await fetch(apiUrl(path), init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(payload.detail || `HTTP ${response.status}`, response.status);
  return payload as T;
}

export function createConversationApi() {
  return {
    create: (input: { kind?: string; source?: Record<string, any> }) => jsonRequest<ConversationSummary>("/conversations", "POST", input),
    list: (query = "", cursor?: string, sourceFamily?: "ai" | "finance") => jsonRequest<{ items: ConversationSummary[]; nextCursor: string | null }>(`/conversations?q=${encodeURIComponent(query)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}${sourceFamily ? `&sourceFamily=${encodeURIComponent(sourceFamily)}` : ""}`),
    get: (id: string) => jsonRequest<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`),
    update: (id: string, title: string) => jsonRequest<ConversationSummary>(`/conversations/${encodeURIComponent(id)}`, "PATCH", { title }),
    remove: (id: string) => jsonRequest<{ ok: boolean }>(`/conversations/${encodeURIComponent(id)}`, "DELETE"),
    export: async (id: string) => {
      const response = await fetch(apiUrl(`/conversations/${encodeURIComponent(id)}/export`), { credentials: "include", headers: authHeaders("GET") });
      if (!response.ok) throw new ApiError(`HTTP ${response.status}`, response.status);
      return response.text();
    },
    import: (sourceKey: string, messages: Array<Record<string, any>>) => jsonRequest<{ conversationId: string; imported: boolean }>("/conversations/import", "POST", { sourceKey, messages }),
    start: (id: string, input: any) => jsonRequest<{ runId: string; status: string }>(`/conversations/${encodeURIComponent(id)}/turns`, "POST", input),
    cancel: (runId: string) => jsonRequest<{ ok: boolean }>(`/runs/${encodeURIComponent(runId)}/cancel`, "POST"),
    events: async (runId: string, after: number, onEvent: (event: any) => void, signal: AbortSignal) => {
      const response = await fetch(apiUrl(`/runs/${encodeURIComponent(runId)}/events?after=${after}`), { credentials: "include", headers: authHeaders("GET"), signal });
      if (!response.ok) throw new ApiError(`HTTP ${response.status}`, response.status);
      if (!response.body) throw new ApiError("后端无响应流", 502);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n"); buffer = lines.pop() || "";
          for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
        }
        buffer += decoder.decode();
        if (buffer.trim()) onEvent(JSON.parse(buffer));
      } finally { reader.releaseLock(); }
    },
  };
}
