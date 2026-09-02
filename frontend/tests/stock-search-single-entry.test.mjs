import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
const input = await read("../src/components/stock/StockSearchInput.tsx");
const detail = await read("../src/pages/StockDetail.tsx");
const watchlist = await read("../src/pages/Watchlist.tsx");
const intel = await read("../src/pages/Intel.tsx");

test("shared stock search uses a white high-contrast field and result panel", () => {
  assert.match(input, /bg-white/);
  assert.match(input, /text-slate-900/);
  assert.match(input, /border-slate-200/);
  assert.match(input, /hover:bg-slate-50/);
});

test("watchlist exposes one search entry while daily review does not include deleted watch controls", () => {
  assert.match(watchlist, /StockSearchInput/);
  assert.doesNotMatch(watchlist, /StockBatchPicker/);
  assert.doesNotMatch(watchlist, /<textarea/);
  assert.ok(watchlist.includes("navigate(`/finance/stocks/${result.code}`)"));
});

test("stock detail keeps a visible add-to-watchlist action", () => {
  assert.match(detail, /加入自选股/);
  assert.match(detail, /已加入自选股/);
  assert.match(detail, /addCodes/);
  assert.match(detail, /saveWatch/);
  assert.doesNotMatch(detail, /hidden lg:inline/);
});

test("empty watchlist guidance points users to stock detail", () => {
  assert.doesNotMatch(intel, /每日复盘.*加自选/);
  assert.match(intel, /详情页|搜索股票/);
});
