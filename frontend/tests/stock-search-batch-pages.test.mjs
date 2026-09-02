import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const [review, watchlist] = await Promise.all([
  readFile(new URL("../src/pages/DailyReview.tsx", import.meta.url), "utf8"),
  readFile(new URL("../src/pages/Watchlist.tsx", import.meta.url), "utf8"),
]);

test("daily review has no deleted watch controls", () => {
  assert.doesNotMatch(review, /StockSearchInput|saveWatch|refreshWatch|关注股票/);
});

test("watchlist uses one search entry and keeps page-owned watch persistence", () => {
  assert.match(watchlist, /StockSearchInput/);
  assert.doesNotMatch(watchlist, /StockBatchPicker/);
  assert.doesNotMatch(watchlist, /<textarea/);
  assert.match(watchlist, /saveWatch/);
  assert.ok(watchlist.includes("navigate(`/finance/stocks/${result.code}`)"));
});

test("watchlist page no longer writes new codes outside stock detail", () => {
  assert.doesNotMatch(watchlist, /parseCodes|addCodes/);
});
