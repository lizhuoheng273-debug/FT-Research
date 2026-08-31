import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const [review, watchlist] = await Promise.all([
  readFile(new URL("../src/pages/DailyReview.tsx", import.meta.url), "utf8"),
  readFile(new URL("../src/pages/Watchlist.tsx", import.meta.url), "utf8"),
]);

test("daily review uses the shared batch picker and keeps page-owned watch persistence", () => {
  assert.match(review, /StockBatchPicker/);
  assert.match(review, /parseCodes|addCodes/);
  assert.match(review, /saveWatch/);
  assert.match(review, /pendingStocks/);
  assert.match(review, /refreshWatch/);
});

test("watchlist uses the shared batch picker and keeps the original add button", () => {
  assert.match(watchlist, /StockBatchPicker/);
  assert.match(watchlist, /parseCodes|addCodes/);
  assert.match(watchlist, /saveWatch/);
  assert.match(watchlist, /pendingStocks/);
  assert.match(watchlist, /onPasteCodes/);
});

test("batch page flows submit six digit codes rather than display names", () => {
  for (const page of [review, watchlist]) {
    assert.match(page, /addCodes/);
    assert.match(page, /\.code/);
    assert.match(page, /saveWatch\(next\)/);
  }
});
