import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

async function loadRefresher() {
  const source = await readFile(new URL("../src/lib/rssRefresh.ts", import.meta.url), "utf8");
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, AbortController, Promise });
  return exports.createRssRefresher;
}

const source = (id) => ({ id, name: id, category: "tech", region: "cn", priority: 1, homepage: "", stale: false, items: [] });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((next, fail) => { resolve = next; reject = fail; });
  return { promise, resolve, reject };
};

test("refreshes different cards independently while duplicate clicks share one request", async () => {
  const createRssRefresher = await loadRefresher();
  const a = deferred(); const b = deferred();
  const calls = [];
  const seen = [];
  const refresher = createRssRefresher((item) => { calls.push(item.id); return item.id === "a" ? a.promise : b.promise; }, (item) => seen.push(item.id));
  const firstA = refresher.refresh(source("a"));
  const secondA = refresher.refresh(source("a"));
  const firstB = refresher.refresh(source("b"));
  assert.equal(calls.join(","), "a,b");
  assert.equal(refresher.isRefreshing("a"), true);
  assert.equal(refresher.isRefreshing("b"), true);
  b.resolve(source("b")); a.resolve(source("a"));
  await Promise.all([firstA, secondA, firstB]);
  assert.deepEqual(seen.sort(), ["a", "b"]);
  assert.equal(refresher.isRefreshing("a"), false);
});

test("failed request keeps the existing list because it does not emit a replacement", async () => {
  const createRssRefresher = await loadRefresher();
  const original = source("a"); original.items = [{ id: "old", title: "旧文章", originalUrl: "https://example.com/old" }];
  let displayed = original;
  const refresher = createRssRefresher(() => Promise.reject(new Error("timeout")), (item) => { displayed = item; });
  await assert.rejects(refresher.refresh(original), /timeout/);
  assert.equal(displayed.items[0].title, "旧文章");
});

test("dispose aborts requests and ignores late source callbacks", async () => {
  const createRssRefresher = await loadRefresher();
  const pending = deferred();
  const seen = [];
  const refresher = createRssRefresher(() => pending.promise, (item) => seen.push(item.id));
  const running = refresher.refresh(source("a"));
  refresher.dispose();
  pending.resolve(source("a"));
  await running;
  assert.deepEqual(seen, []);
});
