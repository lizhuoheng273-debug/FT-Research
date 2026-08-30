import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const stockData = await readFile(new URL("../src/pages/StockData.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("stock research search accepts names and exposes selectable suggestions", () => {
  assert.match(stockData, /股票代码或名称/);
  assert.match(stockData, /stockSearch/);
  assert.match(stockData, /搜索结果/);
});

test("stock search API is query encoded", () => {
  assert.match(api, /stockSearch:\s*\(query: string/);
  assert.match(api, /encodeURIComponent\(query\)/);
});
