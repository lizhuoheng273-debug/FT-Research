import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const page = await readFile(new URL("../src/pages/AINews.tsx", import.meta.url), "utf8");
const feed = await readFile(new URL("../src/components/ai/AISubscriptionFeed.tsx", import.meta.url), "utf8");
const sortableCard = await readFile(new URL("../src/components/ai/RssSortableCard.tsx", import.meta.url), "utf8").catch(() => "");
const trash = await readFile(new URL("../src/components/ai/RssTrashDialog.tsx", import.meta.url), "utf8").catch(() => "");
const state = await readFile(new URL("../src/lib/rssSubscriptions.ts", import.meta.url), "utf8");
const hot = await readFile(new URL("../src/components/ai/AIHotFeed.tsx", import.meta.url), "utf8");
const daily = await readFile(new URL("../src/pages/AIDaily.tsx", import.meta.url), "utf8");
const feedAndCard = `${feed}\n${sortableCard}`;

const compiledState = ts.transpileModule(state, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function loadStateModule(initial = {}) {
  const values = new Map(Object.entries(initial));
  const localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const exports = {};
  vm.runInNewContext(compiledState, { exports, window: { localStorage }, JSON, Math, Map, Set });
  return { api: exports, values };
}

const plain = (value) => JSON.parse(JSON.stringify(value));

test("AI news keeps the hotspot board but replaces duplicate event cards with media subscriptions", () => {
  assert.match(page, /AIHotFeed[\s\S]*showEvents=\{false\}/);
  assert.match(page, /AISubscriptionFeed/);
  assert.doesNotMatch(page, /精选事件/);
  assert.match(state, /ithome.*qbitai.*jiqizhixin.*zhidx.*xinzhiyuan.*tmtpost.*huxiu.*solidot.*baijingapp.*williamlong/s);
  assert.match(feedAndCard, /items\.slice\(0,\s*3\)/);
  assert.match(feedAndCard, /originalUrl/);
  assert.match(feedAndCard, /target="_blank"/);
  assert.match(hot, /showEvents\??:\s*boolean/);
  assert.match(daily, /<AIHotFeed topics=\{topics\} items=\{items\}/);
});

test("subscription state persists order, pin, hide and custom sources locally", () => {
  assert.match(state, /localStorage/);
  assert.match(state, /ithome.*qbitai.*jiqizhixin.*zhidx.*xinzhiyuan.*tmtpost.*huxiu.*solidot.*baijingapp.*williamlong/s);
  for (const token of ["order", "pinned", "hidden", "custom", "resetSubscriptions", "removeCustomSource"]) assert.match(state, new RegExp(token));
});

test("subscription feed has search targeting and accessible fallback reorder controls", () => {
  for (const token of ["scrollIntoView", "highlightedId", "onKeyDown", "上移", "下移", "置顶", "隐藏", "恢复默认"]) assert.match(feed, new RegExp(token));
  assert.match(feed, /POST|\/ai\/rss\/resolve/);
});

test("subscription feed uses dnd-kit for pointer, touch and keyboard sorting", () => {
  for (const token of ["DndContext", "SortableContext", "PointerSensor", "TouchSensor", "KeyboardSensor", "DragOverlay", "useSortable", "activationConstraint", "autoScroll", "sortableKeyboardCoordinates", "verticalListSortingStrategy", "arrayMove"]) {
    assert.match(feedAndCard, new RegExp(token));
  }
  assert.match(feedAndCard, /distance:\s*6/);
  assert.match(feedAndCard, /delay:\s*200/);
  assert.match(feedAndCard, /tolerance:\s*8/);
  assert.match(feedAndCard, /onDragEnd/);
  assert.match(feedAndCard, /active\.id[\s\S]*over\.id/);
  assert.match(feedAndCard, /data-no-drag/);
  assert.doesNotMatch(feedAndCard, /\bdraggable\b/);
  assert.doesNotMatch(feedAndCard, /onPointerUp/);
});

test("subscription cards keep actions below content on narrow screens", () => {
  assert.match(feedAndCard, /grid-cols-\[auto_minmax\(0,1fr\)\]/);
  assert.match(feedAndCard, /col-span-2[^\"]*flex-wrap/);
  assert.match(feedAndCard, /sm:flex/);
});

test("adding a source uses a centered accessible modal with test then save steps", () => {
  for (const token of ["role=\"dialog\"", "aria-modal=\"true\"", "fixed", "测试连接", "保存并刷新", "名称", "RSS（完整订阅地址）", "previewSource", "Escape"]) assert.match(feed, new RegExp(token));
  assert.doesNotMatch(feed, /Not Found/);
});

test("v1 hidden sources migrate once into v2 trash and preserve active state", () => {
  const legacy = {
    order: ["qbitai", "custom-x"],
    pinned: ["qbitai"],
    hidden: ["ithome"],
    custom: [{ id: "custom-x", name: "X", url: "https://x.test/rss" }],
  };
  const { api, values } = loadStateModule({
    "ft-research:ai-rss-subscriptions:v1": JSON.stringify(legacy),
  });

  const migrated = api.readRssSubscriptionState();

  assert.equal(migrated.version, 2);
  assert.deepEqual(plain(migrated.order), legacy.order);
  assert.deepEqual(plain(migrated.pinned), legacy.pinned);
  assert.deepEqual(plain(migrated.custom), legacy.custom);
  assert.deepEqual(plain(migrated.trash), [{ id: "ithome", kind: "builtin", previousIndex: 0, wasPinned: false }]);
  assert.deepEqual(JSON.parse(values.get("ft-research:ai-rss-subscriptions:v2")), plain(migrated));
});

test("batch trash removes builtin and custom sources while retaining custom metadata", () => {
  const { api } = loadStateModule();
  const state = {
    version: 2,
    order: ["ithome", "custom-x", "qbitai"],
    pinned: ["custom-x", "qbitai"],
    custom: [{ id: "custom-x", name: "X", url: "https://x.test/rss" }],
    trash: [{ id: "solidot", kind: "builtin", previousIndex: 3, wasPinned: false }],
  };

  const trashed = api.trashSubscriptions(state, ["ithome", "custom-x"]);

  assert.deepEqual(plain(trashed.order), ["qbitai"]);
  assert.deepEqual(plain(trashed.pinned), ["qbitai"]);
  assert.deepEqual(plain(trashed.custom), []);
  assert.deepEqual(plain(trashed.trash), [
    state.trash[0],
    { id: "ithome", kind: "builtin", previousIndex: 0, wasPinned: false },
    { id: "custom-x", kind: "custom", previousIndex: 1, wasPinned: true, custom: state.custom[0] },
  ]);
});

test("single restore returns custom metadata, pin state and a clamped position without duplicates", () => {
  const { api } = loadStateModule();
  const custom = { id: "custom-x", name: "X", url: "https://x.test/rss" };
  const state = {
    version: 2,
    order: ["qbitai", "solidot", "qbitai"],
    pinned: ["qbitai", "qbitai"],
    custom: [],
    trash: [{ id: "custom-x", kind: "custom", previousIndex: 99, wasPinned: true, custom }],
  };

  const restored = api.restoreSubscriptions(state, ["custom-x", "custom-x"]);

  assert.deepEqual(plain(restored.order), ["qbitai", "solidot", "custom-x"]);
  assert.deepEqual(plain(restored.pinned), ["qbitai", "custom-x"]);
  assert.deepEqual(plain(restored.custom), [custom]);
  assert.deepEqual(plain(restored.trash), []);
});

test("restore-all restores every trashed source and orderRssSources hides trash", () => {
  const { api } = loadStateModule();
  const state = {
    version: 2,
    order: ["qbitai"],
    pinned: [],
    custom: [],
    trash: [
      { id: "ithome", kind: "builtin", previousIndex: 0, wasPinned: false },
      { id: "custom-x", kind: "custom", previousIndex: 1, wasPinned: false, custom: { id: "custom-x", name: "X", url: "https://x.test/rss" } },
    ],
  };
  const sources = ["ithome", "qbitai", "custom-x"].map((id) => ({ id, name: id }));

  assert.deepEqual(plain(api.orderRssSources(sources, state).map((source) => source.id)), ["qbitai"]);
  const restored = api.restoreAllSubscriptions(state);
  assert.deepEqual(plain(restored.order), ["ithome", "custom-x", "qbitai"]);
  assert.equal(restored.trash.length, 0);
});

test("repeated reads are idempotent and malformed storage falls back to defaults", () => {
  const legacy = { order: ["qbitai"], pinned: [], hidden: ["ithome"], custom: [] };
  const migratedContext = loadStateModule({
    "ft-research:ai-rss-subscriptions:v1": JSON.stringify(legacy),
  });
  const first = migratedContext.api.readRssSubscriptionState();
  const second = migratedContext.api.readRssSubscriptionState();
  assert.deepEqual(plain(second), plain(first));
  assert.equal(migratedContext.values.get("ft-research:ai-rss-subscriptions:v1"), JSON.stringify(legacy));

  const malformed = loadStateModule({ "ft-research:ai-rss-subscriptions:v2": "{not-json" });
  assert.deepEqual(plain(malformed.api.readRssSubscriptionState()), plain(malformed.api.defaultRssSubscriptionState()));
});

test("parseable malformed v1 fields fall back to default subscriptions", () => {
  const { api, values } = loadStateModule({
    "ft-research:ai-rss-subscriptions:v1": JSON.stringify({ order: "bad" }),
  });

  assert.deepEqual(plain(api.readRssSubscriptionState()), plain(api.defaultRssSubscriptionState()));
  assert.equal(values.get("ft-research:ai-rss-subscriptions:v2"), undefined);
});

test("mismatched custom trash metadata makes v2 storage fall back to defaults", () => {
  const { api } = loadStateModule({
    "ft-research:ai-rss-subscriptions:v2": JSON.stringify({
      version: 2,
      order: [],
      pinned: [],
      custom: [],
      trash: [{ id: "x", kind: "custom", previousIndex: 0, wasPinned: false, custom: { id: "y", name: "Y", url: "https://y.test/rss" } }],
    }),
  });

  assert.deepEqual(plain(api.readRssSubscriptionState()), plain(api.defaultRssSubscriptionState()));
});

test("batch restore sorts trash entries by original position before reinserting", () => {
  const { api } = loadStateModule();
  const state = {
    version: 2,
    order: ["c"],
    pinned: [],
    custom: [],
    trash: [
      { id: "b", kind: "builtin", previousIndex: 1, wasPinned: false },
      { id: "a", kind: "builtin", previousIndex: 0, wasPinned: false },
    ],
  };

  const restored = api.restoreSubscriptions(state, ["b", "a"]);

  assert.deepEqual(plain(restored.order), ["a", "b", "c"]);
});

test("batch RSS management and recycle bin expose the restore-only accessible contract", () => {
  const feedAndTrash = `${feed}\n${trash}`;

  for (const text of ["批量管理", "移入回收站", "回收站", "恢复所选", "全部恢复"]) {
    assert.match(feedAndTrash, new RegExp(text));
  }
  for (const token of ["managing", "selectedIds", "trashOpen", "trashSelectedIds", "trashSubscriptions", "restoreSubscriptions", "restoreAllSubscriptions", "window.confirm"]) {
    assert.match(feedAndTrash, new RegExp(token));
  }
  assert.match(feedAndTrash, /aria-modal="true"/);
  assert.doesNotMatch(feedAndTrash, /永久删除/);
});

test("restore and reset notify the parent to refetch sources from the updated local state", () => {
  assert.match(feed, /onSubscriptionSourcesChanged\?: \(state: RssSubscriptionState, change\?: \{ removedSourceIds\?: string\[\] \}\) => void \| Promise<void>/);
  assert.match(feed, /const nextState = restoreSubscriptions\(subscriptionState, trashSelectedIds\)/);
  assert.match(feed, /const nextState = restoreAllSubscriptions\(subscriptionState\)/);
  assert.match(feed, /const nextState = resetSubscriptions\(\)/);
  assert.equal(feed.match(/onSubscriptionSourcesChanged\?\.\(nextState/g)?.length, 3);
  assert.match(page, /const load = async \(subscriptionStateOverride\?: RssSubscriptionState\)/);
  assert.match(page, /subscriptionStateOverride \?\? readRssSubscriptionState\(\)/);
  assert.match(page, /onSubscriptionSourcesChanged=\{\(state, change\) =>/);
  assert.match(page, /void load\(state\)/);
});

test("reset synchronously removes pre-reset custom cards before the parent refetch", () => {
  const { api } = loadStateModule();
  const sources = [{ id: "custom-x", name: "X" }, { id: "qbitai", name: "QbitAI" }];

  assert.equal(typeof api.removeRssSourcesById, "function");
  assert.deepEqual(plain(api.removeRssSourcesById(sources, ["custom-x"])), [sources[1]]);
  assert.match(feed, /const removedSourceIds = subscriptionState\.custom\.map\(\(source\) => source\.id\)/);
  assert.match(feed, /onSubscriptionSourcesChanged\?\.\(nextState, \{ removedSourceIds \}\)/);

  const parentSync = page.slice(page.indexOf("<AISubscriptionFeed"));
  assert.match(parentSync, /removeRssSourcesById\(current, removedSourceIds\)/);
  assert.ok(parentSync.indexOf("setRssSources((current) => removeRssSourcesById") < parentSync.indexOf("void load(state)"));
});
