import assert from "node:assert/strict";
import test from "node:test";

const values = new Map([["vr-watchlist", '["000001"]']]);
globalThis.localStorage = {
  getItem: (key) => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: (key) => values.delete(key),
};
globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
globalThis.window = { dispatchEvent() {} };

const { loadWatch, saveWatch } = await import("../src/lib/watchlist.ts");

test("visitor watchlist starts with Moutai and Zhongji Xuchuang without reading administrator data", () => {
  const visitor = { id: "guest-watch-a", kind: "guest" };
  assert.deepEqual(loadWatch(visitor), ["600519", "300308"]);
  saveWatch(["600519"], visitor);
  assert.deepEqual(loadWatch(visitor), ["600519"]);
  assert.equal(values.get("vr-watchlist"), '["000001"]');
  assert.equal(values.has("ft:owner:watchlist"), false);
});

test("administrator watchlist migrates legacy local data into its private key", () => {
  const administrator = { id: "owner", kind: "owner" };
  assert.deepEqual(loadWatch(administrator), ["000001"]);
  assert.equal(values.get("ft:owner:watchlist"), '["000001"]');
  saveWatch(["000001", "600519"], administrator);
  assert.deepEqual(loadWatch(administrator), ["000001", "600519"]);
});

test("a different visitor session receives its own default watchlist", () => {
  assert.deepEqual(loadWatch({ id: "guest-watch-b", kind: "guest" }), ["600519", "300308"]);
});
