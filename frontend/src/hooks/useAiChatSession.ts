import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createConversationApi } from "@/lib/conversationApi";
import { createConversationClient } from "@/lib/conversationClient";
import type { ConversationProgress } from "@/lib/conversationClient";
import type { AnalysisScope, ChatMsg } from "@/lib/llm";
import { storageGet, storageRemove, storageSet } from "@/lib/storage";
import { defaultReasoningEffort, isReasoningEffort, readReasoningEffort, saveReasoningEffort } from "@/lib/reasoningEffort";
import type { ReasoningEffort } from "@/lib/reasoningEffort";

export interface ToolUse { name: string; arg?: string; status?: string; message?: string; elapsedMs?: number }
export type StoredMsg = ChatMsg & { tools?: ToolUse[]; partial?: boolean; status?: string };
export interface AiChatSession {
  reasoningEffort?: ReasoningEffort; setReasoningEffort?: (effort: ReasoningEffort) => void; reasoningLocked?: boolean;
  conversationId?: string; messages: StoredMsg[]; input: string; setInput: (value: string) => void; loading: boolean; error: string | null; historyLoading?: boolean; contextReady?: boolean; retry?: () => void;
  progress: ConversationProgress | null; toolUses: ToolUse[]; send: (text: string) => Promise<void>; stop: () => void; clearChat: () => void;
}

const api = createConversationApi();
const client = createConversationClient(api);
const conversations = new Map<string, string>();
const CHAT_KEY_PREFIX = "vr-askai-chat:";
const MAX_PERSISTED_MSGS = 40;
const MAX_REQUEST_MSGS = 20;

// Compatibility helpers retained for the explicit, owner-confirmed legacy
// migration screen. Normal guest/owner runs below never read these keys.
export function completeTurns(msgs: StoredMsg[]): StoredMsg[] {
  const out: StoredMsg[] = [];
  for (const message of msgs) {
    if (message.partial) { if (out.length && out[out.length - 1].role === "user") out.pop(); continue; }
    out.push(message);
  }
  return out;
}
export function boundedCompleteTurns(msgs: StoredMsg[], limit: number): StoredMsg[] { return completeTurns(msgs).slice(-limit); }
export function saveLegacyChat(key: string, msgs: StoredMsg[]): void {
  if (!msgs.length) {
    storageRemove(key);
    return;
  }
  const keep = completeTurns(msgs);
  storageSet(key, JSON.stringify(keep.slice(-MAX_PERSISTED_MSGS)));
}
export function removeLegacyChat(legacyKey: string): void { storageRemove(legacyKey); }
export function readLegacyChat(key: string): StoredMsg[] {
  const raw = storageGet(key);
  try {
    const parsed = JSON.parse(raw || "null");
    return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.content === "string") : [];
  } catch { return []; }
}
export const legacyStreamContract = { chatStream: true, onDelta: true, partial: true, MAX_REQUEST_MSGS, boundedCompleteTurns, CHAT_KEY_PREFIX };
export function legacyHistory(msgs: StoredMsg[]): ChatMsg[] {
  return boundedCompleteTurns(msgs, MAX_REQUEST_MSGS).map(({ role, content }) => ({ role, content }));
}
export function makePartialAssistant(): StoredMsg {
  return { role: "assistant", content: "", tools: [], partial: true };
}
export function completeAssistant(message: StoredMsg): StoredMsg {
  const { partial: _drop, ...rest } = message;
  return rest;
}
export async function legacyStreamCleanup(activeController: AbortController | null, ac: AbortController, startedKey: string, chatKey: string, messages: StoredMsg[]): Promise<void> {
  const abortRef = { current: activeController };
  const chatKeyRef = { current: chatKey };
  try { await Promise.resolve(); } catch (e) {
    const superseded = abortRef.current !== null && abortRef.current !== ac;
    if (!superseded && chatKeyRef.current === startedKey) {
      const current = messages;
      const last = current[current.length - 1];
      const dropUser = current[current.length - 2]?.role === "user";
      if (!last || last.role !== "assistant") current.slice(0, dropUser ? -2 : -1);
    }
  } finally { /* request identity cleanup is complete */ }
}

export function resetConversationIdentity() {
  client.resetIdentity();
  conversations.clear();
}

export function useAiChatSession({ conversationKey, conversationId, context, analysisScope = "general", source, contextReady = true }: {
  conversationKey: string; conversationId?: string; context: string; analysisScope?: AnalysisScope; source?: Record<string, any>; contextReady?: boolean;
}): AiChatSession {
  const [id, setId] = useState(() => conversationId || conversations.get(conversationKey) || "");
  const sourceType = String(source?.type || conversationKey);
  const [reasoningEffort, setEffort] = useState<ReasoningEffort>(() => readReasoningEffort(id, defaultReasoningEffort(sourceType, Boolean(id))));
  const [state, setState] = useState(() => client.snapshot(id));
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const pending = useRef(false);
  const epoch = useRef(0);
  const scope = conversationKey + "|" + (conversationId || "");
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  useLayoutEffect(() => {
    epoch.current++;
    pending.current = false;
    setSubmitting(false); setPendingQuestion(""); setError(null); setInput("");
    const next = conversationId || conversations.get(conversationKey) || "";
    setEffort(readReasoningEffort(next, defaultReasoningEffort(sourceType, Boolean(next))));
    setId(next); setState(client.snapshot(next));
  }, [conversationKey, conversationId]);
  useLayoutEffect(() => {
    if (!id) { setState(client.snapshot("")); return; }
    let active = true;
    const detach = client.attach(id, snapshot => { if (active) setState(snapshot); });
    return () => { active = false; detach(); };
  }, [id, retryKey]);
  useEffect(() => () => { epoch.current++; }, []);
  const loading = submitting || state.status === "running" || state.status === "queued" || Boolean(state.activeRunId);
  const ready = contextReady || Boolean(conversationId && state.conversation.contextSnapshot);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || loading || pending.current || !ready || state.historyLoading || state.error) return;
    const version = epoch.current;
    // Freeze this turn before any network await; later choices affect the next turn.
    const turnEffort = reasoningEffort;
    const current = () => epoch.current === version && scopeRef.current === scope;
    pending.current = true;
    setInput(""); setError(null); setSubmitting(true); setPendingQuestion(question);
    let target = id;
    try {
      if (!target) {
        const created = await api.create({ kind: "chat", source: source || { type: conversationKey } });
        if (!current()) return;
        target = created.id; conversations.set(conversationKey, target); setId(target);
        saveReasoningEffort(target, turnEffort);
      }
      const savedContext = conversationId ? client.snapshot(target).conversation.contextSnapshot : null;
      setPendingQuestion("");
      await client.send(target, { clientRequestId: crypto.randomUUID(), question, context: savedContext || { text: context, analysisScope }, reasoningEffort: turnEffort });
      if (current()) setState(client.snapshot(target));
      if (typeof window !== "undefined") window.dispatchEvent(new Event("ft-conversations-changed"));
    } catch (reason) {
      if (current()) setError(reason instanceof Error ? reason.message : "对话失败");
    } finally {
      if (current()) { pending.current = false; setSubmitting(false); setPendingQuestion(""); }
    }
  };
  const stop = () => {
    epoch.current++; pending.current = false; setSubmitting(false); setPendingQuestion("");
    if (id) void client.stop(id).catch(reason => setError(reason instanceof Error ? reason.message : "停止失败"));
  };
  const clearChat = () => {
    epoch.current++; pending.current = false;
    conversations.delete(conversationKey);
    setEffort(defaultReasoningEffort(sourceType));
    setId(""); setState(client.snapshot("")); setInput(""); setError(null); setSubmitting(false); setPendingQuestion("");
  };
  useEffect(() => {
    setElapsed(0);
    if (!state.progress?.startedAt) return;
    const started = state.progress.startedAt;
    const timer = window.setInterval(() => setElapsed(Date.now() - started), 1000);
    return () => window.clearInterval(timer);
  }, [state.progress?.startedAt]);
  useEffect(() => {
    if (["completed", "stopped", "error", "interrupted"].includes(state.status)) window.dispatchEvent(new Event("ft-conversations-changed"));
  }, [state.status]);
  const progress = submitting ? { phase: "submit", status: "running", message: "正在提交请求…" } :
    state.progress ? { ...state.progress, elapsedMs: Math.max(elapsed, state.progress.elapsedMs || 0) } : null;
  const messages = pendingQuestion ? [...state.messages, { role: "user" as const, content: pendingQuestion }] : state.messages;
  const setReasoningEffort = (effort: ReasoningEffort) => {
    if (!isReasoningEffort(effort) || submitting) return;
    setEffort(effort); saveReasoningEffort(id, effort);
  };
  return { conversationId: id || undefined, messages: messages as StoredMsg[], input, setInput, loading, error: error || state.error,
    reasoningEffort, setReasoningEffort, reasoningLocked: submitting,
    historyLoading: state.historyLoading, contextReady: ready, retry: () => { setError(null); setRetryKey(value => value + 1); },
    progress, toolUses: state.toolUses, send, stop, clearChat };
}
