import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const stockData = await readFile(new URL("../src/pages/StockData.tsx", import.meta.url), "utf8");
const stockInput = await readFile(new URL("../src/components/stock/StockSearchInput.tsx", import.meta.url), "utf8");
const stockHook = await readFile(new URL("../src/hooks/useStockSearch.ts", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("stock research search accepts names and exposes selectable suggestions", () => {
  assert.match(stockData, /股票代码或名称/);
  assert.match(stockData, /StockSearchInput/);
  assert.match(stockInput, /搜索中|暂无匹配股票/);
  assert.match(stockHook, /api\.stockSearch/);
});

test("stock search API is query encoded", () => {
  assert.match(api, /stockSearch:\s*\(query: string/);
  assert.match(api, /encodeURIComponent\(query\)/);
});
