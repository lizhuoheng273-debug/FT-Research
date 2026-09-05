// 关注股票（自选股）—— 管理员存本地，访客仅保存在当前内存会话。
// 行情复用 /api/quote；复盘时把关注股行情一并喂给用户自己的 AI。

import { getAuthIdentity, type AuthIdentity } from "./authClient.ts";

const LEGACY_KEY = "vr-watchlist";
const OWNER_KEY = "ft:owner:watchlist";
const VISITOR_DEFAULTS = ["600519", "300308"];
const visitorLists = new Map<string, string[]>();

function validCodes(raw: string | null): string[] {
  try {
    const value = JSON.parse(raw || "[]");
    return Array.isArray(value) ? value.filter((code) => /^\d{6}$/.test(code)) : [];
  } catch {
    return [];
  }
}

export function loadWatch(identity: Pick<AuthIdentity, "id" | "kind"> | null = getAuthIdentity()): string[] {
  if (identity?.kind === "guest") {
    if (!visitorLists.has(identity.id)) visitorLists.set(identity.id, [...VISITOR_DEFAULTS]);
    return [...(visitorLists.get(identity.id) || VISITOR_DEFAULTS)];
  }
  if (identity?.kind !== "owner") return [];
  try {
    const privateValue = localStorage.getItem(OWNER_KEY);
    if (privateValue !== null) return validCodes(privateValue);
    const legacy = validCodes(localStorage.getItem(LEGACY_KEY));
    localStorage.setItem(OWNER_KEY, JSON.stringify(legacy));
    return legacy;
  } catch {
    return [];
  }
}

export function saveWatch(codes: string[], identity: Pick<AuthIdentity, "id" | "kind"> | null = getAuthIdentity()) {
  const normalized = Array.from(new Set(codes.filter((code) => /^\d{6}$/.test(code))));
  if (identity?.kind === "guest") {
    visitorLists.set(identity.id, normalized);
  } else if (identity?.kind === "owner") {
    // localStorage 在隐私模式 / 嵌入式浏览器 / 配额写满时会抛异常。
    // 存不下就算了——自选丢失总好过整页崩掉（读取侧同样是 try/catch 兜底）。
    try {
      localStorage.setItem(OWNER_KEY, JSON.stringify(normalized));
    } catch {
      /* 存储不可用：本次会话内仍可正常使用，只是关掉页面后不保留 */
    }
  }
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("vr-watchlist-updated"));
}

// 从任意文本里抽取 6 位 A 股代码（逗号 / 空格 / 换行 / 顿号分隔都行，方便一次粘贴一串）。
export function parseCodes(raw: string): string[] {
  const tokens = raw.split(/[^\d]+/).filter(Boolean);
  return Array.from(new Set(tokens.filter((t) => /^\d{6}$/.test(t))));
}

// 把用户输入的一串代码并入已有自选，返回去重后的新列表 + 实际新增数量。
export function addCodes(existing: string[], raw: string): { next: string[]; added: number } {
  const incoming = parseCodes(raw).filter((c) => !existing.includes(c));
  return { next: [...existing, ...incoming], added: incoming.length };
}
