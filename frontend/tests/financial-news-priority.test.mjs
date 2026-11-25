import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../src/pages/FinancialNews.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/pages/FinancialNewsDetail.tsx", import.meta.url), "utf8");
const eventPage = await readFile(new URL("../src/pages/FinancialEventDetail.tsx", import.meta.url), "utf8");
const workspace = await readFile(new URL("../src/pages/FinanceAiWorkspace.tsx", import.meta.url), "utf8");
const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("financial news renders dual-edition financial daily and upcoming calendar", () => {
  assert.match(page, /金融日报/);
  assert.match(page, /今日金融头条/);
  assert.match(page, /本期看点/);
  assert.match(page, /<UpcomingEvents/);
  for (const removed of ["紧要快讯", "A股热门事件榜", "全球观察", "全部资讯流", "GlobalMarketStrip", "financialNewsFollowing", "loadWatch"]) {
    assert.doesNotMatch(page, new RegExp(removed));
  }
  assert.match(page, /financialDailyLatest/);
  assert.match(page, /financialNewsCalendar/);
});

test("news snapshot refresh cancels prior requests and has a finite deadline", () => {
  assert.match(page, /AbortController/);
  assert.match(page, /controller\.abort/);
  assert.match(page, /60000/);
});

test("financial story detail links into full tracked event timeline and keeps original links", () => {
  assert.match(router, /\/finance\/news\/story\/:eventId/);
  assert.match(router, /\/finance\/news\/event\/:storyId/);
  for (const label of ["事实摘要", "事件后续", "查看完整事件"]) assert.match(detail, new RegExp(label));
  for (const label of ["先了解这件事", "事件进展", "为什么热", "报道时间线", "热度趋势"]) assert.match(eventPage, new RegExp(label));
  assert.match(detail, /safeHref/);
  for (const removed of ["A股传导路径", "紧要分依据", "热度分依据", "市场证据"]) assert.doesNotMatch(detail, new RegExp(removed));
});

test("frontend exposes financial daily, report detail, and tracked event endpoints", () => {
  assert.match(api, /financialDailyLatest/);
  assert.match(api, /financialNewsReportDetail/);
  assert.match(api, /financialNewsTrackedEvent/);
  assert.match(api, /financialNewsFollowing/);
  assert.match(api, /finance\/news\/following/);
  assert.match(api, /pageSize/);
});

test("AI workspace uses financial daily and tracked event context for finance news", () => {
  assert.match(workspace, /financialDailyLatest/);
  assert.match(workspace, /financialNewsTrackedEvent/);
  assert.match(workspace, /financialNewsCalendar/);
  assert.doesNotMatch(workspace, /financialNewsFollowing/);
  assert.doesNotMatch(workspace, /A股热门/);
});
