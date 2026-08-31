import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const input = await readFile(new URL("../src/components/stock/StockSearchInput.tsx", import.meta.url), "utf8");

test("renders A-share candidate metadata and selection callbacks", () => {
  assert.match(input, /result\.name/);
  assert.match(input, /result\.code/);
  assert.match(input, /A股/);
  assert.match(input, /onSelect/);
});

test("supports keyboard navigation, selection, escape and outside click", () => {
  for (const marker of ["ArrowDown", "ArrowUp", "Enter", "Escape", "mousedown", "contains"]) {
    assert.match(input, new RegExp(marker));
  }
});

test("submits only a complete six digit code in A-share mode", () => {
  assert.match(input, /normalizeAStockCode/);
  assert.match(input, /onSubmitCode/);
  assert.match(input, /allowExternalSymbols/);
});
