import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const root = new URL("../src/", import.meta.url);
const router = fs.readFileSync(new URL("router.tsx", root), "utf8");
const detail = fs.readFileSync(new URL("pages/StockDetail.tsx", root), "utf8");
const layout = fs.readFileSync(new URL("components/layout/Layout.tsx", root), "utf8");
const workspaceUrl = new URL("pages/FinanceAiWorkspace.tsx", root);
const conversationUrl = new URL("components/ai/AiConversation.tsx", root);
const sessionUrl = new URL("hooks/useAiChatSession.ts", root);
const quoteHookUrl = new URL("hooks/useLiveStockQuote.ts", root);

test("stock header opens a dedicated AI workspace and preserves return state", () => {
  assert.match(router, /\/finance\/ai/);
  assert.match(router, /\/finance\/stocks\/:code\/ai[\s\S]*FinanceAiWorkspace/);
  assert.match(detail, /to=\{`\/finance\/ai\?source=stock&code=\$\{code\}`\}/);
  assert.match(detail, /state=\{\{ from(?:\s*:|\s*\})/);
  assert.doesNotMatch(detail, /label="让 AI 读这只"/);
});

test("AI workspace provides a wide responsive research layout", () => {
  assert.ok(fs.existsSync(workspaceUrl));
  const workspace = fs.readFileSync(workspaceUrl, "utf8");
  assert.match(workspace, /Finance AI Workspace/);
  assert.match(workspace, /AiConversation/);
  assert.match(workspace, /行情/);
  assert.match(workspace, /按需查询|按需重新读取/);
  assert.match(workspace, /ConversationRail/);
  assert.doesNotMatch(workspace, /已带入上下文|工具调用记录/);
  assert.match(workspace, /lg:grid-cols/);
  assert.match(workspace, /h-\[calc\(100dvh-1\.5rem\)\]/);
  assert.match(workspace, /min-h-0 flex-1/);
  assert.match(layout, /stockAiWorkspace/);
  assert.match(layout, /max-w-none/);
  assert.ok(fs.existsSync(quoteHookUrl));
  assert.match(workspace, /api\.marketChart|api\.quote/);
  assert.match(detail, /useLiveStockQuote/);
});

test("shared conversation keeps streaming and exposes an explicit stop action", () => {
  assert.ok(fs.existsSync(conversationUrl));
  assert.ok(fs.existsSync(sessionUrl));
  const conversation = fs.readFileSync(conversationUrl, "utf8");
  const session = fs.readFileSync(sessionUrl, "utf8");
  assert.match(conversation, /停止生成/);
  // Partial-answer saving is covered by the rendered conversation and
  // conversation-presentation behavior tests, not an implementation regex.
  assert.match(conversation, /stop\(\)/);
  assert.match(session, /chatStream/);
  assert.match(session, /onDelta/);
  assert.match(session, /partial: true/);
  assert.match(session, /AbortController/);
  assert.match(session, /MAX_REQUEST_MSGS/);
  assert.match(session, /boundedCompleteTurns\(msgs, MAX_REQUEST_MSGS\)/);
});

test("returning from a linked workspace does not add a browser-history loop", () => {
  const workspace = fs.readFileSync(workspaceUrl, "utf8");
  assert.match(workspace, /stateFrom/);
  assert.match(workspace, /navigate\(source === "stock"/);
});

test("stock conversations use a versioned key without migrating legacy framework history", () => {
  const workspace = fs.readFileSync(workspaceUrl, "utf8");
  const session = fs.readFileSync(sessionUrl, "utf8");
  assert.match(workspace, /buildFinanceAiKey/);
  assert.doesNotMatch(workspace, /legacyConversationKey:/);
  assert.match(session, /export function readLegacyChat/);
  assert.match(session, /storageRemove\(legacyKey\)/);
});

test("workspace uses typed AI status without changing the backend chat contract", () => {
  const api = fs.readFileSync(new URL("lib/api.ts", root), "utf8");
  const workspace = fs.readFileSync(workspaceUrl, "utf8");
  assert.match(api, /interface AiStatus/);
  assert.match(api, /aiStatus:/);
  assert.match(api, /\/ai\/status/);
  assert.match(workspace, /api\.aiStatus\(\)/);
  assert.doesNotMatch(workspace, /apiKey/);
});
