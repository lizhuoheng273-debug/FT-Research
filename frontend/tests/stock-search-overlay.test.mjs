import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const input = await readFile(new URL("../src/components/stock/StockSearchInput.tsx", import.meta.url), "utf8");

test("renders stock search results in a viewport-level overlay", () => {
  assert.match(input, /createPortal/);
  assert.match(input, /getBoundingClientRect/);
  assert.match(input, /position:\s*["']fixed["']/);
});

test("keeps the overlay anchored while the viewport changes", () => {
  assert.match(input, /addEventListener\("resize"/);
  assert.match(input, /addEventListener\("scroll"/);
  assert.match(input, /capture: true/);
});
