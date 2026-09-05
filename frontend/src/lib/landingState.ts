import type { AuthIdentity } from "@/lib/authClient";

export function landingPrimaryAction(identity: AuthIdentity | null) {
  if (identity) return { kind: "workspace" as const, label: "进入工作台", to: "/ai/news" as const };
  return { kind: "guest" as const, label: "以访客身份体验" };
}
