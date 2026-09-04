import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");
const css = await read("index.css");
const stockSearch = await read("components/stock/StockSearchInput.tsx");
const aiConversation = await read("components/ai/AiConversation.tsx");
const rail = await read("components/ai/ConversationRail.tsx");
const router = await read("router.tsx");
const aiNews = await read("pages/AINews.tsx");
const destination = await read("lib/conversationDestination.ts");

test("input surfaces expose theme-aware tokens for both themes", () => {
  assert.match(css, /--input:/);
  assert.match(css, /\.light\s*\{[\s\S]*--input:/);
  assert.match(stockSearch, /bg-input/);
  assert.match(stockSearch, /text-input-foreground/);
  assert.match(aiConversation, /bg-input/);
  assert.match(aiConversation, /text-input-foreground/);
});

test("AI board opens a filtered second-level conversation workspace", () => {
  assert.match(aiNews, /workspaceSource=["']ai-news["']/);
  assert.match(router, /path:\s*["']\/ai\/conversations["'][\s\S]*AiConversationWorkspace/);
  assert.match(rail, /sourceFamily/);
  assert.match(destination, /ai-news|ai-daily/);
  assert.match(destination, /\/ai\/conversations/);
});
