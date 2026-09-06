import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";
import vm from "node:vm";

async function loadApi() {
  const source = await readFile(new URL("../src/lib/aiNewsStory.ts", import.meta.url), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(output, {
    AbortController,
    DOMException,
    Promise,
    clearTimeout,
    setTimeout,
    require: (specifier) => {
      if (specifier === "@/lib/api") return { apiUrl: (path) => `/api${path}`, authHeaders: () => ({}) };
      throw new Error(`Unexpected module: ${specifier}`);
    },
    module,
    exports: module.exports,
  });
  return module.exports;
}

const topic = (overrides = {}) => ({
  id: "topic-1",
  title: "原始标题",
  links: {},
  ...overrides,
});

const item = (overrides = {}) => ({
  id: "item-1",
  title: "条目标题",
  summary: "摘要",
  links: {},
  ...overrides,
});

test("storyPublicId prefers topic and item story links before the topic id", async () => {
  const api = await loadApi();
  assert.equal(api.storyPublicId(topic({ links: { story: "https://x/stories/topic-public" } }), item({ links: { story: "https://x/stories/item-public" } })), "topic-public");
  assert.equal(api.storyPublicId(topic(), item({ links: { story: "https://x/stories/item-public?utm=1#top" } })), "item-public");
  assert.equal(api.storyPublicId(topic()), "topic-1");
});

test("findStoryFallback matches story id, original link, exact id, then normalized title", async () => {
  const api = await loadApi();
  const byStory = item({ id: "wrong", links: { story: "https://x/stories/public-1" }, title: "无关标题" });
  assert.equal(api.findStoryFallback(topic({ links: { story: "https://x/stories/public-1" } }), [byStory])?.summary, "摘要");

  const byOriginal = item({ id: "wrong", links: { original: "https://example.com/article" } });
  assert.equal(api.findStoryFallback(topic({ links: { original: "https://example.com/article" } }), [byOriginal])?.id, "wrong");

  const byId = item({ id: "topic-1", title: "另一标题" });
  assert.equal(api.findStoryFallback(topic(), [byId])?.id, "topic-1");

  const byTitle = item({ id: "different", title: "  同一，新闻！ " });
  assert.equal(api.findStoryFallback(topic({ title: "同一 新闻" }), [byTitle])?.id, "different");
});

test("loadAiNewsStory retries twice and returns the third successful response", async () => {
  const api = await loadApi();
  let calls = 0;
  const story = await api.loadAiNewsStory("public-1", {
    fetcher: async () => (++calls < 3 ? Promise.reject(new Error("gateway")) : { story: { title: "成功" } }),
    retries: 2,
    retryDelayMs: 0,
  });
  assert.equal(calls, 3);
  assert.equal(story.title, "成功");
});

test("loadAiNewsStory rejects after the configured total attempts", async () => {
  const api = await loadApi();
  let calls = 0;
  await assert.rejects(
    api.loadAiNewsStory("public-1", {
      fetcher: async () => { calls += 1; throw new Error("gateway"); },
      retries: 2,
      retryDelayMs: 0,
    }),
    /gateway/,
  );
  assert.equal(calls, 3);
});

test("loadAiNewsStory never retries an abort error", async () => {
  const api = await loadApi();
  let calls = 0;
  const controller = new AbortController();
  await assert.rejects(
    api.loadAiNewsStory("public-1", {
      signal: controller.signal,
      fetcher: async () => { calls += 1; throw new DOMException("aborted", "AbortError"); },
      retries: 2,
      retryDelayMs: 0,
    }),
    (error) => error.name === "AbortError",
  );
  assert.equal(calls, 1);
});

test("loadAiNewsStory stops a pending request when its signal is aborted", async () => {
  const api = await loadApi();
  const controller = new AbortController();
  let calls = 0;
  const pending = api.loadAiNewsStory("public-1", {
    signal: controller.signal,
    fetcher: async () => { calls += 1; return new Promise(() => {}); },
    retries: 2,
    retryDelayMs: 0,
  });
  controller.abort();
  await assert.rejects(pending, (error) => error.name === "AbortError");
  assert.equal(calls, 1);
});

test("prefetchAiNewsStory deduplicates requests and exposes the same promise", async () => {
  const api = await loadApi();
  let resolve;
  let calls = 0;
  const fetcher = async () => { calls += 1; return new Promise((next) => { resolve = next; }); };
  const first = api.prefetchAiNewsStory("public-1", { fetcher, retries: 0, retryDelayMs: 0 });
  const second = api.prefetchAiNewsStory("public-1", { fetcher, retries: 0, retryDelayMs: 0 });
  assert.strictEqual(first, second);
  assert.strictEqual(api.takePrefetchedAiNewsStory("public-1"), first);
  await Promise.resolve();
  resolve({ title: "预取成功" });
  assert.equal((await first).title, "预取成功");
  assert.equal(calls, 1);
});

test("prefetchAiNewsStory removes rejected entries so a later interaction can retry", async () => {
  const api = await loadApi();
  let calls = 0;
  const fetcher = async () => {
    calls += 1;
    if (calls === 1) throw new Error("temporary");
    return { title: "第二次成功" };
  };
  await assert.rejects(api.prefetchAiNewsStory("public-2", { fetcher, retries: 0, retryDelayMs: 0 }), /temporary/);
  assert.equal(api.takePrefetchedAiNewsStory("public-2"), undefined);
  assert.equal((await api.prefetchAiNewsStory("public-2", { fetcher, retries: 0, retryDelayMs: 0 })).title, "第二次成功");
  assert.equal(calls, 2);
});
