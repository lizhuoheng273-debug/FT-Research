import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const batch = await readFile(new URL("../src/components/stock/StockBatchPicker.tsx", import.meta.url), "utf8");

test("batch picker forms name plus code tags and supports repeated selection", () => {
  assert.match(batch, /items/);
  assert.match(batch, /item\.name/);
  assert.match(batch, /item\.code/);
  assert.match(batch, /onItemsChange/);
});

test("batch picker allows deleting tags and delegates raw paste to the page", () => {
  assert.match(batch, /onPasteCodes/);
  assert.match(batch, /filter/);
  assert.match(batch, /删除|移除/);
});

test("batch picker keeps storage outside the shared component", () => {
  assert.doesNotMatch(batch, /localStorage/);
  assert.doesNotMatch(batch, /saveWatch/);
});
