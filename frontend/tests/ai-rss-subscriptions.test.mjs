import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../src/pages/AINews.tsx", import.meta.url), "utf8");
const feed = await readFile(new URL("../src/components/ai/AISubscriptionFeed.tsx", import.meta.url), "utf8");
const state = await readFile(new URL("../src/lib/rssSubscriptions.ts", import.meta.url), "utf8");
const hot = await readFile(new URL("../src/components/ai/AIHotFeed.tsx", import.meta.url), "utf8");
const daily = await readFile(new URL("../src/pages/AIDaily.tsx", import.meta.url), "utf8");

test("AI news keeps the hotspot board but replaces duplicate event cards with media subscriptions", () => {
  assert.match(page, /AIHotFeed[\s\S]*showEvents=\{false\}/);
  assert.match(page, /AISubscriptionFeed/);
  assert.doesNotMatch(page, /精选事件/);
  assert.match(state, /ithome.*qbitai.*jiqizhixin.*zhidx.*xinzhiyuan.*tmtpost.*huxiu.*solidot.*baijingapp.*williamlong/s);
  assert.match(feed, /items\.slice\(0,\s*3\)/);
  assert.match(feed, /originalUrl/);
  assert.match(feed, /target="_blank"/);
  assert.match(hot, /showEvents\??:\s*boolean/);
  assert.match(daily, /<AIHotFeed topics=\{topics\} items=\{items\}/);
});

test("subscription state persists order, pin, hide and custom sources locally", () => {
  assert.match(state, /localStorage/);
  assert.match(state, /ithome.*qbitai.*jiqizhixin.*zhidx.*xinzhiyuan.*tmtpost.*huxiu.*solidot.*baijingapp.*williamlong/s);
  for (const token of ["order", "pinned", "hidden", "custom", "resetSubscriptions", "removeCustomSource"]) assert.match(state, new RegExp(token));
});

test("subscription feed has search targeting and accessible pointer/keyboard reorder controls", () => {
  for (const token of ["scrollIntoView", "highlightedId", "onPointerDown", "onPointerUp", "draggable", "onKeyDown", "上移", "下移", "置顶", "隐藏", "恢复默认"]) assert.match(feed, new RegExp(token));
  assert.match(feed, /POST|\/ai\/rss\/resolve/);
});

test("subscription cards keep actions below content on narrow screens", () => {
  assert.match(feed, /grid-cols-\[auto_minmax\(0,1fr\)\]/);
  assert.match(feed, /col-span-2[^\"]*flex-wrap/);
  assert.match(feed, /sm:flex/);
});

test("adding a source uses a centered accessible modal with test then save steps", () => {
  for (const token of ["role=\"dialog\"", "aria-modal=\"true\"", "fixed", "测试连接", "保存并刷新", "名称", "RSS（完整订阅地址）", "previewSource", "Escape"]) assert.match(feed, new RegExp(token));
  assert.doesNotMatch(feed, /Not Found/);
});
