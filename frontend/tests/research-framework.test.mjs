import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const root = new URL("../src/", import.meta.url);
const read = (path) => fs.readFileSync(new URL(path, root), "utf8");
const llm = read("lib/llm.ts");
const session = read("hooks/useAiChatSession.ts");
const askAi = read("components/ui/AskAiButton.tsx");
const daily = read("pages/DailyReview.tsx");
const index = read("pages/IndexDetail.tsx");
const sector = read("pages/SectorDetail.tsx");
const stockWorkspace = read("pages/FinanceAiWorkspace.tsx");
const stockData = read("pages/StockData.tsx");
const stockTabs = read("components/stock/StockResearchTabs.tsx");

test("chat request sends an explicit analysis scope instead of method ids", () => {
  assert.match(llm, /type AnalysisScope = "general" \| "market" \| "index" \| "sector" \| "stock"/);
  assert.match(llm, /analysis_scope: analysisScope/);
  assert.doesNotMatch(llm, /method_ids/);
  assert.match(session, /analysisScope/);
});

test("the shared AI panel has no blogger method selector", () => {
  assert.doesNotMatch(askAi, /ResearchMethodSelect|methodId|researchMethods/);
  assert.match(askAi, /analysisScope/);
});

test("the four research page types provide their explicit default scope", () => {
  assert.match(daily, /analysisScope="market"/);
  assert.match(index, /analysisScope="index"/);
  assert.match(sector, /analysisScope="sector"/);
  assert.match(stockWorkspace, /scopeFor/);
  assert.match(stockData, /analysisScope="stock"/);
  assert.match(stockTabs, /analysisScope="stock"/);
});

test("daily review sends the full objective market context", () => {
  for (const marker of ["marketReview", "breadth", "liquidity", "shortTermEmotion", "turnoverTop", "sectors", "数据缺口"]) {
    assert.match(daily, new RegExp(marker));
  }
  assert.doesNotMatch(daily, /globalIndices|globalIdx/);
});

test("new framework conversations use a versioned key", () => {
  assert.match(askAi, /framework:v2/);
  assert.match(stockWorkspace, /buildFinanceAiKey/);
});
