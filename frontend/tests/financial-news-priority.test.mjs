import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../src/pages/FinancialNews.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/pages/FinancialNewsDetail.tsx", import.meta.url), "utf8");
const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/components/layout/Layout.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("finance navigation puts daily review before financial news", () => {
  assert.ok(layout.indexOf('label: "每日复盘"') < layout.indexOf('label: "金融市场资讯"'));
});

test("financial news shows urgent hot watchlist and a filterable feed", () => {
  for (const label of ["紧要快讯", "热门事件榜", "我的关注", "全部资讯流", "本站计算"]) {
    assert.match(page, new RegExp(label));
  }
  assert.match(page, /slice\(0,\s*urgentExpanded \? 10 : 5\)/);
  assert.match(page, /slice\(0,\s*hotExpanded \? 10 : 5\)/);
  assert.match(page, /api\.financialNewsOverview/);
  assert.match(page, /api\.announcements/);
  assert.match(page, /api\.news/);
});

test("financial event detail has scoring timeline sources and streaming AI entry", () => {
  assert.match(router, /\/finance\/news\/story\/:eventId/);
  for (const label of ["评分依据", "影响范围", "相关报道时间线", "原始来源", "AI 摘要与追问"]) {
    assert.match(detail, new RegExp(label));
  }
  assert.match(detail, /AskAiButton/);
});

test("frontend exposes typed financial news endpoints", () => {
  for (const path of ["finance/news/overview", "finance/news/feed", "finance/news/events", "finance/news/status"]) {
    assert.match(api, new RegExp(path.replaceAll("/", "\\/")));
  }
  for (const field of ["urgencyScore", "hotScore", "scoreReasons", "relatedSourceCount", "relatedStocks"]) {
    assert.match(api, new RegExp(field));
  }
});
