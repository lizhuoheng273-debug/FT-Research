import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { chatStream, type ChatMsg } from "@/lib/llm";
import { storageGet, storageRemove, storageSet } from "@/lib/storage";

const CHAT_KEY_PREFIX = "vr-askai-chat:";
const MAX_PERSISTED_MSGS = 40;
const MAX_REQUEST_MSGS = 20;

export interface ToolUse { name: string; arg: string }

export type StoredMsg = ChatMsg & {
  tools?: ToolUse[];
  partial?: boolean;
};

function argStr(args: Record<string, unknown>): string {
  if (Array.isArray(args.codes)) return (args.codes as unknown[]).join(",");
  if (typeof args.code === "string") return args.code;
  return "";
}

function parseChat(raw: string | null): StoredMsg[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (message): message is StoredMsg =>
        message && typeof message === "object" && typeof message.content === "string" &&
        (message.role === "user" || message.role === "assistant"),
    );
  } catch {
    return [];
  }
}

function loadChat(key: string, legacyConversationKey?: string): StoredMsg[] {
  const currentRaw = storageGet(key);
  if (currentRaw) return parseChat(currentRaw);
  if (!legacyConversationKey) return [];
  const legacyKey = CHAT_KEY_PREFIX + legacyConversationKey;
  const legacyRaw = storageGet(legacyKey);
  const migrated = parseChat(legacyRaw);
  if (migrated.length) {
    storageSet(key, JSON.stringify(migrated.slice(-MAX_PERSISTED_MSGS)));
    storageRemove(legacyKey);
  }
  return migrated;
}

function completeTurns(msgs: StoredMsg[]): StoredMsg[] {
  const out: StoredMsg[] = [];
  for (const message of msgs) {
    if (message.partial) {
      if (out.length && out[out.length - 1].role === "user") out.pop();
      continue;
    }
    out.push(message);
  }
  return out;
}

function boundedCompleteTurns(msgs: StoredMsg[], limit: number): StoredMsg[] {
  const recent = completeTurns(msgs).slice(-limit);
  return recent[0]?.role === "assistant" ? recent.slice(1) : recent;
}

function saveChat(key: string, msgs: StoredMsg[]): void {
  if (!msgs.length) {
    storageRemove(key);
    return;
  }
  const keep = completeTurns(msgs);
  if (!keep.length) {
    storageRemove(key);
    return;
  }
  storageSet(key, JSON.stringify(keep.slice(-MAX_PERSISTED_MSGS)));
}

export interface AiChatSession {
  messages: StoredMsg[];
  input: string;
  setInput: (value: string) => void;
  loading: boolean;
  error: string | null;
  toolUses: ToolUse[];
  send: (text: string) => Promise<void>;
  stop: () => void;
  clearChat: () => void;
}

export function useAiChatSession({ conversationKey, legacyConversationKey, context }: {
  conversationKey: string;
  legacyConversationKey?: string;
  context: string;
}): AiChatSession {
  const chatKey = CHAT_KEY_PREFIX + conversationKey;
  const [chat, setChat] = useState<{ key: string; msgs: StoredMsg[] }>(
    () => ({ key: chatKey, msgs: loadChat(chatKey, legacyConversationKey) }),
  );
  const msgs = chat.msgs;
  const setMsgs = (updater: StoredMsg[] | ((previous: StoredMsg[]) => StoredMsg[])) =>
    setChat((current) => ({
      key: current.key,
      msgs: typeof updater === "function" ? updater(current.msgs) : updater,
    }));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const chatKeyRef = useRef(chatKey);
  chatKeyRef.current = chatKey;

  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setError(null);
    setChat({ key: chatKey, msgs: loadChat(chatKey, legacyConversationKey) });
  }, [chatKey, legacyConversationKey]);

  useEffect(() => {
    if (chat.key !== chatKey) return;
    saveChat(chatKey, chat.msgs);
  }, [chatKey, chat]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const stop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
  };

  const clearChat = () => {
    stop();
    setError(null);
    setMsgs([]);
  };

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || loading) return;
    setInput("");
    setError(null);
    const history: ChatMsg[] = [
      ...boundedCompleteTurns(msgs, MAX_REQUEST_MSGS).map(({ role, content }) => ({ role, content })),
      { role: "user", content: question },
    ];
    setMsgs((current) => [
      ...current,
      { role: "user", content: question },
      { role: "assistant", content: "", tools: [], partial: true },
    ]);
    setLoading(true);
    const patchLast = (update: (message: StoredMsg) => StoredMsg) =>
      setMsgs((current) => current.map((message, index) =>
        index === current.length - 1 && message.role === "assistant" ? update(message) : message,
      ));
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    const startedKey = chatKeyRef.current;
    const alive = () => abortRef.current === ac && !ac.signal.aborted;
    try {
      await chatStream(history, context, {
        onTool: (tool, args) => {
          if (alive()) patchLast((message) => ({ ...message, tools: [...(message.tools || []), { name: tool, arg: argStr(args) }] }));
        },
        onDelta: (textChunk) => {
          if (alive()) patchLast((message) => ({ ...message, content: message.content + textChunk }));
        },
      }, ac.signal);
      if (alive()) patchLast((message) => {
        const { partial: _drop, ...rest } = message;
        return rest;
      });
    } catch (e) {
      const superseded = abortRef.current !== null && abortRef.current !== ac;
      if (!superseded && chatKeyRef.current === startedKey) {
        setMsgs((current) => {
          const last = current[current.length - 1];
          if (!last || last.role !== "assistant" || last.content) return current;
          const dropUser = current[current.length - 2]?.role === "user";
          return current.slice(0, dropUser ? -2 : -1);
        });
        if (!ac.signal.aborted) setError(e instanceof ApiError ? e.message : "对话失败");
      }
    } finally {
      if (abortRef.current === ac) {
        abortRef.current = null;
        setLoading(false);
      }
    }
  };

  const toolUses = useMemo(() => msgs.flatMap((message) => message.tools || []), [msgs]);
  return { messages: msgs, input, setInput, loading, error, toolUses, send, stop, clearChat };
}
