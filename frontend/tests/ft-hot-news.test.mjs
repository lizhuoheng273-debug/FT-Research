import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const news = await readFile(new URL("../src/pages/AINews.tsx", import.meta.url), "utf8");
const sharedFeed = await readFile(new URL("../src/components/ai/AIHotFeed.tsx", import.meta.url), "utf8");
const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/components/layout/Layout.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/pages/AINewsDetail.tsx", import.meta.url), "utf8");

test("AI hotspot page uses a 5-to-10 expandable board and detail cards", () => {
  assert.match(layout, /AI 热点资讯/);
  assert.match(news, /hot-topics/);
  assert.match(sharedFeed, /slice\(0,\s*expanded \? 10 : 5\)/);
  assert.match(sharedFeed, /展开全部 10 条/);
  assert.match(news, /\/ai\/news\/story/);
});

test("AI hotspot detail route is registered", () => {
  assert.match(router, /\/ai\/news\/story\/:storyId/);
  for (const section of ["AI 导读", "推荐理由", "标签", "报道时间线", "AI 摘要与追问"]) assert.match(detail, new RegExp(section));
});

test("AI hotspot follow-up opens the full workspace for the selected story", () => {
  assert.match(detail, /<AskAiButton[\s\S]*workspaceSource="ai-news"[\s\S]*workspaceEventId=\{storyId\}/);
  assert.doesNotMatch(detail, /<AskAiButton[^>]*workspaceSource=\{undefined\}/);
});

test("AI hotspot feed prefetches only on intentional pointer and keyboard focus", () => {
  assert.match(sharedFeed, /onPrefetchStory\??\s*:/);
  assert.match(sharedFeed, /onMouseEnter=\{[^}]*onPrefetchStory/);
  assert.match(sharedFeed, /onFocus=\{[^}]*onPrefetchStory/);
  assert.match(sharedFeed, /onTouchStart=\{[^}]*onPrefetchStory/);
  assert.match(sharedFeed, /onPrefetchStory(?:\?\.)?\(topic,\s*item/);
});

test("AI hotspot page uses the shared story identity, fallback and prefetch helpers", () => {
  assert.match(news, /aiNewsStory/);
  assert.match(news, /storyPublicId\(topic,\s*fallback/);
  assert.match(news, /findStoryFallback\(topic,\s*items\)/);
  assert.match(news, /prefetchAiNewsStory\(/);
  assert.match(news, /links:\s*\{\s*original:[\s\S]*story:/);
});

test("AI hotspot detail uses prefetched stories and abortable two-retry loading", () => {
  assert.match(detail, /import\s*\{[^}]*loadAiNewsStory[^}]*takePrefetchedAiNewsStory[^}]*\}\s*from\s*["']@\/lib\/aiNewsStory["']/);
  assert.match(detail, /takePrefetchedAiNewsStory\(storyId\)/);
  assert.match(detail, /loadAiNewsStory\(storyId,\s*\{\s*signal:\s*controller\.signal,\s*retries:\s*2\s*\}\)/s);
  assert.match(detail, /new AbortController\(\)/);
  assert.match(detail, /return\s*\(\)\s*=>\s*\{[\s\S]{0,240}controller\.abort\(\)/);
});

test("AI hotspot detail keeps fallback visible and skeletonizes only missing sections", () => {
  assert.match(detail, /fallback\?\.title/);
  assert.match(detail, /fallback\?\.summary/);
  assert.match(detail, /fallback\?\.source/);
  assert.match(detail, /fallback\?\.links\?\.original/);
  assert.match(detail, /!digest\s*&&\s*loading[\s\S]*?animate-pulse/);
  assert.doesNotMatch(detail, /详情暂不可用/);
});

test("AI hotspot detail offers final recovery and an original-story link", () => {
  assert.match(detail, /完整详情暂时未加载成功/);
  assert.match(detail, /重新加载/);
  assert.match(detail, /查看原文/);
});
