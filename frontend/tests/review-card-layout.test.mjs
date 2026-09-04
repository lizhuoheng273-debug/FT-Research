import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const daily = await readFile(new URL("../src/pages/DailyReview.tsx", import.meta.url), "utf8");
const modal = await readFile(new URL("../src/components/market/MarketReviewModal.tsx", import.meta.url), "utf8");

test("daily review constrains the mobile card track so long turnover rows scroll locally", () => {
  const pair = /<div className="mb-6 grid grid-cols-1 items-stretch gap-4 lg:grid-cols-\[minmax\(0,2fr\)_minmax\(0,3fr\)\]">\s*<button[\s\S]*?className="glass flex h-full w-full flex-col p-4 text-left[^"]*"[\s\S]*?<GlassCard className="h-full min-w-0 p-4">/;
  assert.match(daily, pair);
  assert.doesNotMatch(daily, /mb-6 grid items-start gap-4 lg:grid-cols-\[minmax\(0,2fr\)_minmax\(0,3fr\)\]/);
});

test("market review detail uses opaque theme-card surfaces instead of translucent glass", () => {
  assert.match(modal, /rounded-2xl border border-border bg-card text-card-foreground shadow-2xl/);
  assert.doesNotMatch(modal, /<div className="glass relative z-10/);
  assert.match(daily, /rounded-xl border border-border\/60 bg-card p-3 shadow-sm/);
});
