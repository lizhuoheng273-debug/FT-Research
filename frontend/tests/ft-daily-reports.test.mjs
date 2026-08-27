import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const daily = await readFile(new URL("../src/pages/AIDaily.tsx", import.meta.url), "utf8");
const sharedFeed = await readFile(new URL("../src/components/ai/AIHotFeed.tsx", import.meta.url), "utf8");
const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");

test("AI report center provides daily weekly monthly switching and shareable periods", () => {
  for (const label of ["日报", "周报", "月报"]) assert.match(daily, new RegExp(label));
  assert.match(daily, /api\/ai\/reports\/index/);
  assert.match(daily, /useSearchParams/);
  assert.match(daily, /"weekly"/);
  assert.match(daily, /"monthly"/);
  assert.match(router, /\/ai\/daily/);
});

test("AI report archive uses a dual-column rail with month groups and daily headlines", () => {
  assert.match(daily, /report-layout/);
  assert.match(daily, /按月份归档/);
  assert.match(daily, /headline/);
});

test("daily report reuses hotspot board and story detail navigation", () => {
  assert.match(daily, /hotTopics/);
  assert.match(sharedFeed, /展开全部 10 条/);
  assert.match(daily, /\/ai\/news\/story/);
  assert.match(daily, /stale/);
});

test("period reports render lead stats themes media and original links", () => {
  for (const label of ["本期主线", "主题", "媒体", "打开 AI HOT 原文报告"]) assert.match(daily, new RegExp(label));
  assert.match(daily, /api\/ai\/reports\/\$\{targetKind\}/);
});
