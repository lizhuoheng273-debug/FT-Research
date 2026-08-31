import assert from "node:assert/strict";
import test from "node:test";

import {
  StockSearchTimeoutError,
  runStockSearch,
} from "../src/lib/stock-search-request.ts";

test("a stock search that never settles is rejected at the configured timeout", async () => {
  const neverSettles = (_query, _limit, signal) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });

  await assert.rejects(
    runStockSearch(neverSettles, "600", 8, { timeoutMs: 10 }),
    StockSearchTimeoutError,
  );
});

test("starting a new query can abort the previous stock search", async () => {
  const controller = new AbortController();
  const waitsForAbort = (_query, _limit, signal) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });
  const pending = runStockSearch(waitsForAbort, "贵州", 8, {
    signal: controller.signal,
    timeoutMs: 1_000,
  });

  controller.abort();

  await assert.rejects(pending, (error) => error?.name === "AbortError");
});

test("a successful stock search returns its candidates before the timeout", async () => {
  const candidates = [{ code: "600519", name: "贵州茅台" }];
  const search = async () => candidates;

  assert.deepEqual(
    await runStockSearch(search, "茅台", 8, { timeoutMs: 100 }),
    candidates,
  );
});
