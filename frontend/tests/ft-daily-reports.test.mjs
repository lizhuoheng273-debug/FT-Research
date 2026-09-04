import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const daily = await readFile(new URL("../src/pages/AIDaily.tsx", import.meta.url), "utf8");
const sharedFeed = await readFile(new URL("../src/components/ai/AIHotFeed.tsx", import.meta.url), "utf8");
const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");

test("AI report center provides daily weekly monthly switching and shareable periods", () => {
  for (const label of ["日报", "周报", "月报"]) assert.match(daily, new RegExp(label));
  assert.match(daily, /apiUrl\(/);
  assert.match(daily, /ai\/reports\/index/);
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
  assert.match(daily, /apiUrl\(/);
  assert.match(daily, /ai\/reports\/\$\{targetKind\}/);
});

test("featured event cards expose only title and a real summary", () => {
  assert.doesNotMatch(sharedFeed, /热度 \$\{/);
  assert.doesNotMatch(sharedFeed, /AI HOT<\/a>/);
  assert.doesNotMatch(sharedFeed, /Sparkles/);
  assert.doesNotMatch(sharedFeed, /点击查看事件详情与报道时间线/);
  assert.match(sharedFeed, /buildFeaturedEventCard/);
});

test("featured event cards use a neutral report surface with only a hotspot-sized orange rank", () => {
  assert.doesNotMatch(sharedFeed, /from-primary\/\[0\.07\]/);
  assert.doesNotMatch(sharedFeed, /text-2xl font-bold leading-none text-primary/);
  assert.match(sharedFeed, /w-6 shrink-0 text-center font-mono text-sm font-bold text-primary/);
  assert.match(sharedFeed, /hover:border-border/);
});

test("period stories omit the summary region when summary is absent", () => {
  assert.doesNotMatch(daily, /story\.summary \|\| "暂无摘要"/);
  assert.match(daily, /summary &&/);
  assert.match(daily, /story\.summary\?\.trim\(\)/);
});
