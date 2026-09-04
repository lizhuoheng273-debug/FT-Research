import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../src/pages/FinancialNews.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/pages/FinancialNewsDetail.tsx", import.meta.url), "utf8");
const workspace = await readFile(new URL("../src/pages/FinanceAiWorkspace.tsx", import.meta.url), "utf8");
const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("financial news composes only the hot list and upcoming calendar", () => {
  assert.match(page, /<GlobalHotList/);
  assert.match(page, /<UpcomingEvents/);
  for (const removed of ["紧要快讯", "A股热门事件榜", "全球观察", "全部资讯流", "全球市场", "GlobalMarketStrip", "financialNewsFollowing", "loadWatch"]) {
    assert.doesNotMatch(page, new RegExp(removed));
  }
  assert.match(page, /globalHighlights/);
  assert.match(page, /financialNewsCalendar/);
});

test("news snapshot refresh cancels prior requests and has a finite deadline", () => {
  assert.match(page, /AbortController/);
  assert.match(page, /controller\?\.abort/);
  assert.match(page, /20000/);
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

test("AI workspace uses global highlights and calendar context for finance news", () => {
  assert.match(workspace, /globalHighlights/);
  assert.match(workspace, /financialNewsCalendar/);
  assert.doesNotMatch(workspace, /financialNewsFollowing/);
  assert.doesNotMatch(workspace, /A股热门/);
});
