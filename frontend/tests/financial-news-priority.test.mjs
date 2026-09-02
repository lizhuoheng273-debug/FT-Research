import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../src/pages/FinancialNews.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/pages/FinancialNewsDetail.tsx", import.meta.url), "utf8");
const workspace = await readFile(new URL("../src/pages/FinanceAiWorkspace.tsx", import.meta.url), "utf8");
const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("financial news page has exactly global highlights and following as its two primary sections", () => {
  assert.match(page, /全球要闻速览/);
  assert.match(page, /我的关注/);
  for (const removed of ["紧要快讯", "A股热门事件榜", "全球观察", "全部资讯流", "全球市场", "GlobalMarketStrip"]) {
    assert.doesNotMatch(page, new RegExp(removed));
  }
  assert.match(page, /globalHighlights/);
  assert.match(page, /financialNewsFollowing/);
  assert.match(page, /slice\(0,\s*globalExpanded \? 20 : 10\)/);
  assert.match(page, /事件简述与关键数字/);
  assert.match(page, /来源\/更新时间/);
  assert.match(page, /target="_blank"/);
});

test("following selection changes cancel or ignore the previous request", () => {
  assert.match(page, /AbortController/);
  assert.match(page, /requestVersion/);
  assert.match(page, /loadWatch/);
});

test("financial event detail keeps original links and source evidence", () => {
  assert.match(router, /\/finance\/news\/story\/:eventId/);
  for (const label of ["原文链接暂缺", "原始来源", "相关报道时间线"]) assert.match(detail, new RegExp(label));
  assert.match(detail, /safeHref/);
  assert.match(detail, /sourceTimeline/);
});

test("frontend exposes global highlights and query-only following endpoints", () => {
  assert.match(api, /globalHighlights/);
  assert.match(api, /financialNewsFollowing/);
  assert.match(api, /finance\/news\/following/);
  assert.match(api, /pageSize/);
});

test("AI workspace uses global highlights and following context for finance news", () => {
  assert.match(workspace, /globalHighlights/);
  assert.match(workspace, /financialNewsFollowing/);
  assert.doesNotMatch(workspace, /A股热门/);
});
