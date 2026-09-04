import { storageGet, storageSet } from "./storage";

export type ReasoningEffort = "low" | "high" | "max";
const prefix = "ft-reasoning-effort:";
export function isReasoningEffort(value: unknown): value is ReasoningEffort {
  return value === "low" || value === "high" || value === "max";
}
export function defaultReasoningEffort(sourceType: string, existing = false): ReasoningEffort {
  return !existing && (sourceType.startsWith("ai-") || sourceType.startsWith("/ai/")) ? "high" : "max";
}
export function readReasoningEffort(id: string, fallback: ReasoningEffort): ReasoningEffort {
  const stored = id ? storageGet(prefix + id) : null;
  return isReasoningEffort(stored) ? stored : fallback;
}
export function saveReasoningEffort(id: string, effort: ReasoningEffort): void {
  if (id && isReasoningEffort(effort)) storageSet(prefix + id, effort);
}
