import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const chart = await readFile(new URL("../src/components/market/MarketChart.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("index intraday chart uses nullable average and never draws an unconditional average line", () => {
  assert.match(api, /average:\s*number\s*\|\s*null/);
  assert.match(chart, /data\.asset\s*===\s*["']stock["']/);
  assert.match(chart, /filter\(.*Number\.isFinite/);
  assert.doesNotMatch(chart, /series:\s*\[[\s\S]*\{\s*name:\s*["']均价["'][\s\S]*points\.map\(\(point\)\s*=>\s*point\.average\)/);
});
