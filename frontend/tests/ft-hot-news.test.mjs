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
