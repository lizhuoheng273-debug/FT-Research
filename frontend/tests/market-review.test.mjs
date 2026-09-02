import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const chart = await readFile(new URL("../src/components/market/MarketChart.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const daily = await readFile(new URL("../src/pages/DailyReview.tsx", import.meta.url), "utf8");
const modalUrl = new URL("../src/components/market/MarketReviewModal.tsx", import.meta.url);

test("index intraday chart uses nullable average and never draws an unconditional average line", () => {
  assert.match(api, /average:\s*number\s*\|\s*null/);
  assert.match(chart, /data\.asset\s*===\s*["']stock["']/);
  assert.match(chart, /filter\(.*Number\.isFinite/);
  assert.doesNotMatch(chart, /series:\s*\[[\s\S]*\{\s*name:\s*["']均价["'][\s\S]*points\.map\(\(point\)\s*=>\s*point\.average\)/);
});

test("daily review consumes one snapshot and renders the required section order", () => {
  for (const marker of ["api.marketReview()", "AI 收盘简述", "大盘指数", "市场宽度", "涨停/跌停", "成交额 Top20", "板块资金趋势", "资金轮动"]) {
    assert.match(daily, new RegExp(marker));
  }
  for (const deleted of ["关注股票", "AI 当日复盘", "平盘", "globalIndices", "globalIdx", "api.marketOverview", "api.emotion", "api.turnoverTop"]) {
    assert.doesNotMatch(daily, new RegExp(deleted));
  }
  const order = ["AI 收盘简述", "大盘指数", "市场宽度", "涨停/跌停", "成交额 Top20", "板块资金趋势", "资金轮动"];
  assert.ok(order.every((item, index) => index === 0 || daily.indexOf(item) > daily.indexOf(order[index - 1])));
  assert.match(daily, /slice\(0,\s*10\)/);
  assert.match(daily, /slice\(0,\s*20\)/);
});

test("market review modal is keyboard reachable and responsive", async () => {
  const modal = await readFile(modalUrl, "utf8");
  assert.match(modal, /role=["']dialog["']/);
  assert.match(modal, /aria-modal=["']true["']/);
  assert.match(modal, /Escape/);
  assert.match(modal, /focus/);
  assert.match(modal, /fixed inset-0/);
  assert.match(modal, /sm:max-w/);
  assert.match(modal, /w-full/);
});

test("daily review modal launchers are keyboard-focusable buttons", () => {
  assert.match(daily, /<button\s+type=["']button["'][\s\S]*setModal\("emotion"\)[\s\S]*完整短线情绪/);
  assert.match(daily, /<button\s+type=["']button["'][\s\S]*setModal\("turnover"\)[\s\S]*完整榜单/);
});
