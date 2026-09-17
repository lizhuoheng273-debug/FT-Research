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

const detailPage = await readFile(new URL("../src/pages/AINewsDetail.tsx", import.meta.url), "utf8");

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

test("successful prefetched stories expire and refetch with an injected clock", async () => {
  const api = await loadApi();
  let now = 1_000;
  let calls = 0;
  const clock = () => now;
  const fetcher = async () => ({ title: `版本 ${++calls}` });

  const first = api.prefetchAiNewsStory("expiring-story", { fetcher, retries: 0, retryDelayMs: 0, now: clock, prefetchTtlMs: 100 });
  assert.equal((await first).title, "版本 1");
  now = 1_099;
  assert.strictEqual(api.takePrefetchedAiNewsStory("expiring-story", { now: clock }), first);
  assert.strictEqual(api.prefetchAiNewsStory("expiring-story", { fetcher, retries: 0, retryDelayMs: 0, now: clock, prefetchTtlMs: 100 }), first);

  now = 1_101;
  assert.equal(api.takePrefetchedAiNewsStory("expiring-story", { now: clock }), undefined);
  const second = api.prefetchAiNewsStory("expiring-story", { fetcher, retries: 0, retryDelayMs: 0, now: clock, prefetchTtlMs: 100 });
  assert.notStrictEqual(second, first);
  assert.equal((await second).title, "版本 2");
  assert.equal(calls, 2);
});

test("prefetch cache keeps its ten-story size bound", async () => {
  const api = await loadApi();
  const promises = [];
  for (let index = 0; index < 11; index += 1) {
    promises.push(api.prefetchAiNewsStory(`bounded-${index}`, { fetcher: async () => ({ title: String(index) }), retries: 0 }));
  }
  await Promise.all(promises);
  assert.equal(api.takePrefetchedAiNewsStory("bounded-0"), undefined);
  assert.ok(api.takePrefetchedAiNewsStory("bounded-10"));
});

test("AI story context is deterministically bounded below the conversation payload limit", async () => {
  const api = await loadApi();
  const repeated = "长内容".repeat(4_000);
  const story = {
    title: `关键标题 ${repeated}`,
    digest: `关键摘要 ${repeated}`,
    latest: `关键进展 ${repeated}`,
    links: { original: `https://example.com/main?payload=${"x".repeat(2_000)}` },
    reports: Array.from({ length: 40 }, (_, index) => ({
      title: `报道 ${index + 1} ${repeated}`,
      summary: `报道摘要 ${index + 1} ${repeated}`,
      source: { name: `来源 ${index + 1}` },
      publishedAt: `2026-09-${String(index + 1).padStart(2, "0")}`,
      links: { original: `https://example.com/report-${index + 1}?payload=${"y".repeat(2_000)}` },
    })),
  };

  const built = api.buildAiNewsStoryContext(story);
  assert.ok(built.text.length <= 18_000, `context length was ${built.text.length}`);
  assert.ok(JSON.stringify({ text: built.text, analysisScope: "general" }).length < 24_000);
  assert.match(built.text, /关键标题/);
  assert.match(built.text, /关键摘要/);
  assert.match(built.text, /关键进展/);
  assert.match(built.text, /1\. 报道 1/);
  assert.match(built.text, /https:\/\/example\.com\/main/);
  assert.ok(built.text.indexOf("标题：") < built.text.indexOf("AI 摘要："));
  assert.ok(built.text.indexOf("AI 摘要：") < built.text.indexOf("最新进展："));
  assert.ok(built.text.indexOf("最新进展：") < built.text.indexOf("来源报道："));
  assert.ok(built.text.indexOf("来源报道：") < built.text.indexOf("原文链接："));
});

test("AI detail consumes a cached story before calling the shared retrying loader", () => {
  assert.match(detailPage, /const prefetched = takePrefetchedAiNewsStory\(storyId\);[\s\S]{0,220}const request = prefetched \?\? loadAiNewsStory\(storyId,\s*\{\s*signal:\s*controller\.signal,\s*retries:\s*2\s*\}\)/);
});
