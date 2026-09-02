import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../src/", import.meta.url);
const router = await readFile(new URL("router.tsx", root), "utf8");
const askAi = await readFile(new URL("components/ui/AskAiButton.tsx", root), "utf8");
const financeAi = await readFile(new URL("lib/financeAi.ts", root), "utf8");
const daily = await readFile(new URL("pages/DailyReview.tsx", root), "utf8");
const financial = await readFile(new URL("pages/FinancialNews.tsx", root), "utf8");
const financialDetail = await readFile(new URL("pages/FinancialNewsDetail.tsx", root), "utf8");
const index = await readFile(new URL("pages/IndexDetail.tsx", root), "utf8");
const sector = await readFile(new URL("pages/SectorDetail.tsx", root), "utf8");
const watchlist = await readFile(new URL("pages/Watchlist.tsx", root), "utf8");
const stockData = await readFile(new URL("pages/StockData.tsx", root), "utf8");
const stockDetail = await readFile(new URL("pages/StockDetail.tsx", root), "utf8");

test("finance AI workspace exposes the shared route and all source keys", async () => {
  const workspaceUrl = new URL("pages/FinanceAiWorkspace.tsx", root);
  const workspace = await readFile(workspaceUrl, "utf8");
  assert.match(router, /path:\s*["']\/finance\/ai["']/);
  assert.match(router, /FinanceAiWorkspace/);
  assert.match(router, /\/finance\/stocks\/:code\/ai[\s\S]*FinanceAiWorkspace/);
  for (const source of ["review", "news", "watchlist", "index", "stock", "stock-panel", "news-story"]) assert.match(workspace, new RegExp(`"${source}"`));
  for (const key of ["review:", "news", "news-story:", "watchlist", "index:", "stock:", "stock-panel:"]) assert.match(financeAi, new RegExp(key.replace(/[<>]/g, "\\$&")));
  assert.match(workspace, /useSearchParams/);
  assert.match(workspace, /useAiChatSession/);
  assert.match(workspace, /AiConversation/);
  assert.match(workspace, /state\.from|location\.state/);
  assert.doesNotMatch(workspace, /JSON\.stringify\([^)]*\)\.replace/);
});

test("workspace route target supports source identifiers without putting context in the URL", () => {
  assert.match(askAi, /workspaceSource/);
  assert.match(askAi, /navigate\(/);
  for (const page of [daily, financial, financialDetail, index, sector, watchlist, stockData]) {
    assert.match(page, /workspaceSource=/);
  }
  assert.match(stockDetail, /\/finance\/ai\?source=stock&code=/);
  assert.doesNotMatch(stockDetail, /to=\{`\/finance\/stocks\/\$\{code\}\/ai`\}/);
});
