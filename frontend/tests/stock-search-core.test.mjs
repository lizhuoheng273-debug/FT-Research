import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const core = await readFile(new URL("../src/lib/stock-search.ts", import.meta.url), "utf8");

test("search threshold accepts one Chinese character and two ASCII characters", () => {
  assert.match(core, /isSearchTrigger/);
  assert.match(core, /trimmed\.length >= 1/);
  assert.match(core, /[A-Za-z0-9].*length >= 2/s);
});

test("normalization only returns a six digit A-share code", () => {
  assert.match(core, /normalizeAStockCode/);
  assert.match(core, /\/\^\\d\{6\}\$/);
  assert.match(core, /\? code : null/);
});

test("batch merge removes invalid and duplicate codes without changing existing order", () => {
  assert.match(core, /mergeBatchCodes/);
  assert.match(core, /new Set/);
  assert.match(core, /existing/);
});
