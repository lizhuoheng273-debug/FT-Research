import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

// Execute the real page and its request/state logic; only hook scheduling and
// external HTTP are controlled, without a new DOM/testing dependency.
const source = await readFile(new URL("../src/pages/AINews.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const flush = () => new Promise((resolve) => setImmediate(resolve));
const response = (body) => ({ ok: true, json: async () => body });

function mount(fetch, createRefresher = () => ({ refresh: async () => {}, isRefreshing: () => false, dispose: () => {} })) {
  const cells = [], effects = [], cleanups = [];
  let cursor = 0, mounted = false;
  const react = {
    useState(initial) {
      const key = cursor++;
      if (!(key in cells)) cells[key] = typeof initial === "function" ? initial() : initial;
      return [cells[key], (value) => { cells[key] = typeof value === "function" ? value(cells[key]) : value; }];
    },
    useRef(initial) {
      const key = cursor++;
      return cells[key] ??= { current: initial };
    },
    useEffect(effect) { if (!mounted) effects.push(effect); },
    useMemo(factory) { return factory(); },
  };
  const exports = {};
  vm.runInNewContext(compiled, {
    exports, fetch, Error, AbortController, setTimeout, clearTimeout,
    require(name) {
      if (name === "react") return react;
      if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
      if (name === "react-router-dom") return { useNavigate: () => () => {} };
      if (name === "@/lib/api") return { apiUrl: (path) => `/api${path}`, authHeaders: () => ({}) };
      if (name === "@/lib/rssSubscriptions") return { readRssSubscriptionState: () => ({ custom: [] }) };
      if (name === "@/lib/rssRefresh") return { createRssRefresher: createRefresher };
      return new Proxy({}, { get: (_target, key) => key });
    },
  });
  function render() {
    cursor = 0;
    const tree = exports.AINews();
    if (!mounted) { mounted = true; effects.forEach((effect) => cleanups.push(effect())); }
    return tree;
  }
  function component(type) {
    function find(node) {
      if (Array.isArray(node)) return node.map(find).find(Boolean);
      if (!node || typeof node !== "object") return undefined;
      return node.type === type ? node.props : find(node.props?.children);
    }
    return find(render());
  }
  render();
  return { component, unmount: () => cleanups.forEach((cleanup) => cleanup?.()) };
}

test("RSS refresh outcomes use the exact typed Chinese messages", async () => {
  const initial = { id: "solidot", name: "Solidot", items: [{ id: "old", title: "旧文章" }] };
  const outcomes = [
    { source: { ...initial, items: [...initial.items, { id: "new", title: "新文章" }] }, outcome: "updated", addedCount: 1 },
    { source: { ...initial }, outcome: "current", addedCount: 0 },
    { source: { ...initial }, outcome: "cached", addedCount: 0 },
  ];
  let nextOutcome = 0;
  const app = mount((url) => {
    if (url === "/api/ai/rss/sources") return Promise.resolve(response({ sources: [initial] }));
    if (url === "/api/ai/news/hot-topics" || url.startsWith("/api/ai/news?")) return Promise.resolve(response({ items: [] }));
    if (url === "/api/ai/rss/refresh") return Promise.resolve(response(outcomes[nextOutcome++]));
    throw new Error(`unexpected request: ${url}`);
  }, (request, onResult) => ({
    refresh: async (item) => onResult(await request(item, new AbortController().signal)),
    isRefreshing: () => false,
    dispose: () => {},
  }));
  try {
    await flush(); await flush();
    for (const expected of ["已更新，共新增 1 条", "已是最新内容", "更新未完成，当前显示最近一次成功内容"]) {
      const feed = app.component("AISubscriptionFeed");
      await feed.onRefreshSource(feed.sources[0]);
      assert.equal(app.component("AISubscriptionFeed").refreshMessages.solidot, expected);
    }
  } finally { app.unmount(); }
});

test("a rejected RSS refresh keeps existing articles and shows a genuine failure message", async () => {
  const existing = { id: "solidot", name: "Solidot", items: [{ id: "old", title: "旧文章" }] };
  const app = mount((url) => {
    if (url === "/api/ai/rss/sources") return Promise.resolve(response({ sources: [existing] }));
    if (url === "/api/ai/news/hot-topics" || url.startsWith("/api/ai/news?")) return Promise.resolve(response({ items: [] }));
    if (url === "/api/ai/rss/refresh") return Promise.reject(new Error("RSS offline"));
    throw new Error(`unexpected request: ${url}`);
  }, (request, onResult) => ({
    refresh: async (item) => onResult(await request(item, new AbortController().signal)),
    isRefreshing: () => false,
    dispose: () => {},
  }));
  try {
    await flush(); await flush();
    const feed = app.component("AISubscriptionFeed");
    await feed.onRefreshSource(feed.sources[0]);
    const after = app.component("AISubscriptionFeed");
    assert.equal(after.sources[0].items[0].title, "旧文章");
    assert.equal(after.refreshMessages.solidot, "刷新失败，请稍后重试。");
  } finally { app.unmount(); }
});

test("the page contract names every typed RSS refresh outcome", () => {
  assert.match(source, /已更新，共新增/);
  assert.match(source, /已是最新内容/);
  assert.match(source, /更新未完成，当前显示最近一次成功内容/);
});

test("RSS is displayed while the separate AI HOT requests are still pending", async () => {
  const requests = [];
  const app = mount((url) => {
    requests.push(url);
    if (url === "/api/ai/rss/sources") return Promise.resolve(response({ sources: [{ id: "ithome", name: "IT之家", items: [] }] }));
    return new Promise(() => {});
  });
  try {
    await flush(); await flush();
    assert.ok(requests.includes("/api/ai/rss/sources"));
    const rss = app.component("AISubscriptionFeed");
    assert.equal(rss.loading, false);
    assert.equal(rss.sources[0].name, "IT之家");
    assert.equal(app.component("AIHotFeed").loading, true);
  } finally { app.unmount(); }
});

test("AI HOT failure does not leave the RSS region loading forever", async () => {
  const app = mount((url) => url === "/api/ai/rss/sources"
    ? Promise.resolve(response({ sources: [{ id: "qbitai", name: "量子位", items: [] }] }))
    : Promise.reject(new Error("AI HOT offline")));
  try {
    await flush(); await flush();
    const rss = app.component("AISubscriptionFeed");
    assert.equal(rss.loading, false);
    assert.equal(rss.error, null);
    assert.equal(rss.sources[0].name, "量子位");
  } finally { app.unmount(); }
});

test("RSS failure leaves the hotspot list usable with its own error message", async () => {
  const app = mount((url) => url === "/api/ai/rss/sources"
    ? Promise.reject(new Error("RSS offline"))
    : Promise.resolve(response({ items: [{ id: "event", rank: 1, title: "真实热点" }] })));
  try {
    await flush(); await flush();
    assert.equal(app.component("AIHotFeed").topics[0].title, "真实热点");
    assert.equal(app.component("AISubscriptionFeed").error, "RSS offline");
    assert.equal(app.component("AISubscriptionFeed").loading, false);
  } finally { app.unmount(); }
});
