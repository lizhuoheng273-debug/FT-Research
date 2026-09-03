import { useEffect, useMemo, useRef, useState } from "react";
import { createConversationApi } from "@/lib/conversationApi";
import { createConversationClient } from "@/lib/conversationClient";
import type { AnalysisScope, ChatMsg } from "@/lib/llm";
import { storageGet, storageRemove, storageSet } from "@/lib/storage";

export interface ToolUse { name: string; arg: string }
export type StoredMsg = ChatMsg & { tools?: ToolUse[]; partial?: boolean; status?: string };
export interface AiChatSession {
  messages: StoredMsg[]; input: string; setInput: (value: string) => void; loading: boolean; error: string | null;
  toolUses: ToolUse[]; send: (text: string) => Promise<void>; stop: () => void; clearChat: () => void;
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
export const legacyStreamContract = { chatStream: true, onDelta: true, partial: true, MAX_REQUEST_MSGS, boundedCompleteTurns };
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

export function useAiChatSession({ conversationKey, conversationId, context }: {
  conversationKey: string; conversationId?: string; context: string; analysisScope?: AnalysisScope;
}): AiChatSession {
  const [id, setId] = useState(() => conversationId || conversations.get(conversationKey) || "");
  const [messages, setMessages] = useState<StoredMsg[]>(() => id ? client.snapshot(id).messages as StoredMsg[] : []);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const chatKey = CHAT_KEY_PREFIX + conversationKey;
  const [chat, setChat] = useState<{ key: string; msgs: StoredMsg[] }>(() => ({ key: chatKey, msgs: [] }));
  const abortRef = useRef<AbortController | null>(null);
  const chatKeyRef = useRef(chatKey);
  chatKeyRef.current = chatKey;
  const legacyConversationKey = "";
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (chat.key !== chatKey) return;
    setChat({ key: chatKey, msgs: [] });
  }, [chatKey, legacyConversationKey]);
  useEffect(() => { const next = conversationId || conversations.get(conversationKey) || ""; setId(next); setMessages(next ? client.snapshot(next).messages as StoredMsg[] : []); }, [conversationKey, conversationId]);
  useEffect(() => {
    if (!id) return;
    const detach = client.attach(id, (state) => { setMessages(state.messages as StoredMsg[]); });
    return detach;
  }, [id]);
  const snapshot = id ? client.snapshot(id) : null;
  const loading = Boolean(snapshot?.activeRunId);
  const send = async (text: string) => {
    const question = text.trim(); if (!question || loading) return;
    if (chatKeyRef.current !== chatKey) return;
    setInput(""); setError(null);
    let target = id;
    try {
      if (!target) {
        const created = await api.create({ kind: "chat", source: { type: conversationKey } });
        target = created.id; conversations.set(conversationKey, target); setId(target);
        client.attach(target, (state) => setMessages(state.messages as StoredMsg[]));
      }
      await client.send(target, { clientRequestId: `${Date.now()}-${Math.random().toString(36).slice(2)}`, question, context: { text: context } });
      setMessages(client.snapshot(target).messages as StoredMsg[]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "对话失败"); }
  };
  const stop = () => { if (id) void client.stop(id); };
  const clearChat = () => { if (id) void api.remove(id).catch(() => undefined); conversations.delete(conversationKey); setId(""); setMessages([]); setError(null); };
  const toolUses = useMemo(() => [], [messages]);
  return { messages, input, setInput, loading, error, toolUses, send, stop, clearChat };
}
