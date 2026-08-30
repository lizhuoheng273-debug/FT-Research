// FT-Research AI 对话调用。V1 的 GLM 密钥只在后端环境变量中管理。

import { storageSet, storageRemove } from "@/lib/storage";

import { ApiError, apiUrl, authHeaders } from "./api";
import type { ProviderId } from "./ai-models";

export interface LlmConfig {
  provider: ProviderId;
  baseURL: string; // CLI 订阅时留空
  apiKey?: string;  // 兼容旧版本地配置；V1 不再读取或发送
  model: string;
}

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResult {
  content: string;
  trace: { tool: string; args: Record<string, unknown> }[];
  rounds: number;
}

const KEY = "vr-llm";

export function loadLlm(): LlmConfig | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const c = JSON.parse(raw) as LlmConfig;
    // 清理旧版本可能残留的浏览器密钥，避免误用或继续传播。
    return c.model ? { ...c, apiKey: undefined } : null;
  } catch {
    return null;
  }
}

export function saveLlm(cfg: LlmConfig) {
  storageSet(KEY, JSON.stringify(cfg));
}

export function clearLlm() {
  storageRemove(KEY);
}

export function hasLlm(): boolean {
  // GLM 配置在后端；前端不因浏览器 localStorage 为空而阻断提问。
  return true;
}

export interface ChatHandlers {
  onDelta?: (text: string) => void;             // 答案逐块吐字
  onTool?: (tool: string, args: Record<string, unknown>) => void; // AI 调了某数据工具
}

// 流式调后端 /api/chat（NDJSON：每行一个事件 {type: tool|delta|done|error}）。
// 边流边回调 onDelta/onTool；返回累积的最终 {content, trace, rounds}。
// signal：调用方可传 AbortController.signal，用户关面板/换问题时中止请求（省订阅/API 额度）。
export async function chatStream(messages: ChatMsg[], context: string, handlers: ChatHandlers = {}, signal?: AbortSignal): Promise<ChatResult> {
  let resp: Response;
  try {
    resp = await fetch(apiUrl("/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ messages, context }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e; // 主动中止，原样抛给调用方
    throw new ApiError("连接不到后端，请先启动 backend（uvicorn app:app --port 8900）", 0);
  }
  // 配置错误（缺 key / 未装 CLI）在流开始前以 HTTP 400 返回
  if (!resp.ok) {
    let body: any = null;
    try { body = await resp.json(); } catch { /* ignore */ }
    if (resp.status === 401) {
      throw new ApiError("后端开启了访问鉴权（VR_API_KEY）：请在「接入 AI」页底部填写后端访问密钥", 401);
    }
    throw new ApiError(body?.detail || `HTTP ${resp.status}`, resp.status);
  }
  if (!resp.body) throw new ApiError("后端无响应流", 502);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let content = "";
  let trace: ChatResult["trace"] = [];
  let rounds = 0;
  let errMsg: string | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      let ev: any;
      try { ev = JSON.parse(t); } catch { continue; }
      if (ev.type === "delta") { content += ev.text; handlers.onDelta?.(ev.text); }
      else if (ev.type === "tool") { handlers.onTool?.(ev.tool, ev.args || {}); }
      else if (ev.type === "done") { trace = ev.trace || []; rounds = ev.rounds || 0; }
      else if (ev.type === "error") { errMsg = ev.message; }
    }
  }
  if (errMsg) throw new ApiError(errMsg, 502);
  return { content, trace, rounds };
}

// 非流式便捷包装（不需要逐字 UI 的调用方用它）。
export function chat(messages: ChatMsg[], context: string): Promise<ChatResult> {
  return chatStream(messages, context);
}
