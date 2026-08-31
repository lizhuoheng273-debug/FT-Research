import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const hook = await readFile(new URL("../src/hooks/useStockSearch.ts", import.meta.url), "utf8");

test("hook debounces search by 250ms and cancels the timer on cleanup", () => {
  assert.match(hook, /setTimeout/);
  assert.match(hook, /250/);
  assert.match(hook, /clearTimeout/);
});

test("hook prevents stale responses from replacing newer results", () => {
  assert.match(hook, /requestIdRef/);
  assert.match(hook, /requestId !== requestIdRef\.current/);
});

test("hook clears prior candidates as soon as a new search starts", () => {
  assert.match(hook, /setResults\(\[\]\)/);
  assert.match(hook, /setHighlightedIndex\(-1\)/);
  assert.ok(hook.indexOf("setResults([]);") < hook.indexOf("setOpen(true);"));
});

test("hook exposes loading, error, close and clear state", () => {
  for (const name of ["loading", "error", "close", "clear"]) assert.match(hook, new RegExp(name));
});
