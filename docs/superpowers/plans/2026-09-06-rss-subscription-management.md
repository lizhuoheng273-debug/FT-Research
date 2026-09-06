# RSS Subscription Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RSS refresh results truthful and add recoverable batch deletion plus smooth desktop/mobile card sorting.

**Architecture:** The backend returns an explicit refresh outcome instead of treating cooldown as an HTTP error. Browser-local subscription state moves to a versioned v2 schema with a reversible trash collection. The large feed component delegates management dialogs and sortable cards to focused components built on dnd-kit sensors and a drag overlay.

**Tech Stack:** FastAPI, React 19, TypeScript, localStorage, dnd-kit, Node test runner, pytest

**Spec:** `docs/superpowers/specs/2026-09-06-rss-and-ai-detail-ux-design.md`

## Global Constraints

- RSS ordering, custom sources, pinning and trash remain local to the current browser.
- Do not change administrator/guest permissions or data isolation.
- The trash supports restore only; do not add permanent deletion.
- Interactive news content and action buttons must never activate card dragging.
- Cooldown is a normal `current` result, not a failure.
- Use test-driven development and commit after every independently passing task.

## File Structure

- `backend/app.py`: HTTP refresh outcome and cooldown semantics.
- `backend/tests/test_rss_api.py`: API contract tests for `updated`, `current` and `cached`.
- `frontend/src/lib/rssSubscriptions.ts`: v2 state, migration, trash and restore operations.
- `frontend/src/lib/rssRefresh.ts`: typed refresh result coordination.
- `frontend/src/components/ai/AISubscriptionFeed.tsx`: page-level subscription management state and composition.
- `frontend/src/components/ai/RssSortableCard.tsx`: one sortable card and drag activation boundaries.
- `frontend/src/components/ai/RssTrashDialog.tsx`: recoverable single/batch restore dialog.
- `frontend/src/pages/AINews.tsx`: maps backend refresh outcomes to user-facing messages.
- `frontend/tests/ai-rss-subscriptions.test.mjs`: local-state and component contract tests.
- `frontend/tests/rss-refresh.test.mjs`: refresh coordinator tests.
- `frontend/package.json`, `frontend/package-lock.json`: dnd-kit dependencies.

---

### Task 1: Truthful RSS refresh API

**Files:**
- Modify: `backend/tests/test_rss_api.py`
- Modify: `backend/app.py:243-320`

**Interfaces:**
- Produces: `POST /api/ai/rss/refresh -> { source: RssSource, outcome: "updated" | "current" | "cached", addedCount: number, retryAfter?: number }`

- [ ] **Step 1: Write failing API tests**

Replace the cooldown assertion with a `200` response assertion and add outcome preservation tests:

```python
def test_rss_refresh_returns_current_during_source_cooldown(monkeypatch):
    monkeypatch.setattr(app, "_rss_refresh_attempts", {})
    monkeypatch.setattr(app, "_rss_refresh_clock", lambda: 100.0)
    source = {"id": "solidot", "items": [{"id": "old"}]}
    monkeypatch.setattr(app.rss_catalog, "refresh_source", lambda **_: {
        "source": source, "outcome": "updated", "addedCount": 1,
    })
    monkeypatch.setattr(app.rss_catalog, "source_snapshot", lambda *_args, **_kwargs: source)
    client = TestClient(app.app)
    assert client.post("/api/ai/rss/refresh", json={"sourceId": "solidot"}).status_code == 200
    body = client.post("/api/ai/rss/refresh", json={"sourceId": "solidot"}).json()
    assert body == {"source": source, "outcome": "current", "addedCount": 0, "retryAfter": 30}

def test_rss_refresh_preserves_cached_outcome(monkeypatch):
    monkeypatch.setattr(app, "_rss_refresh_attempts", {})
    monkeypatch.setattr(app.rss_catalog, "refresh_source", lambda **_: {
        "source": {"id": "solidot", "items": [{"id": "old"}]},
        "outcome": "cached", "addedCount": 0,
    })
    body = TestClient(app.app).post("/api/ai/rss/refresh", json={"sourceId": "solidot"}).json()
    assert body["outcome"] == "cached"
```

- [ ] **Step 2: Run the focused backend tests and verify failure**

Run: `python -m pytest backend/tests/test_rss_api.py -q -p no:cacheprovider`

Expected: cooldown test fails because the current endpoint returns `429`.

- [ ] **Step 3: Implement explicit cooldown semantics**

In `backend/app.py`, store the latest source snapshot per refresh identity or obtain it through a focused catalog method. During cooldown return:

```python
return {
    "source": rss_catalog.source_snapshot(source_id, custom_url=custom_url),
    "outcome": "current",
    "addedCount": 0,
    "retryAfter": max(1, math.ceil(remaining)),
}
```

Normalize normal refresh responses so `addedCount` is always an integer and only the three documented outcomes leave the route.

- [ ] **Step 4: Run the focused backend tests**

Run: `python -m pytest backend/tests/test_rss_api.py -q -p no:cacheprovider`

Expected: all RSS API tests pass, including concurrent same-source cooldown with status `200` and one fetch call.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_rss_api.py
git commit -m "fix: report current RSS sources without refresh errors"
```

### Task 2: Versioned local trash state and migration

**Files:**
- Modify: `frontend/src/lib/rssSubscriptions.ts`
- Modify: `frontend/tests/ai-rss-subscriptions.test.mjs`

**Interfaces:**
- Produces: `RssTrashEntry { id, kind, previousIndex, wasPinned, custom? }`
- Produces: `trashSubscriptions(state, sourceIds): RssSubscriptionState`
- Produces: `restoreSubscriptions(state, sourceIds): RssSubscriptionState`
- Produces: `restoreAllSubscriptions(state): RssSubscriptionState`

- [ ] **Step 1: Add executable migration and restore tests**

Transpile the real TypeScript module in a VM with a fake `localStorage`, then assert:

```js
const legacy = { order: ["qbitai", "custom-x"], pinned: ["qbitai"], hidden: ["ithome"], custom: [{ id: "custom-x", name: "X", url: "https://x.test/rss" }] };
localStorage.setItem("ft-research:ai-rss-subscriptions:v1", JSON.stringify(legacy));
const migrated = api.readRssSubscriptionState();
assert.equal(migrated.version, 2);
assert.equal(migrated.trash[0].id, "ithome");

const trashed = api.trashSubscriptions(migrated, ["qbitai", "custom-x"]);
assert.deepEqual(trashed.order, []);
assert.equal(trashed.trash.length, 3);
const restored = api.restoreSubscriptions(trashed, ["custom-x"]);
assert.equal(restored.custom[0].url, "https://x.test/rss");
assert.ok(restored.order.includes("custom-x"));
```

Also test idempotent reads and malformed storage fallback.

- [ ] **Step 2: Run the test and verify failure**

Run: `node --test frontend/tests/ai-rss-subscriptions.test.mjs`

Expected: failures for missing `version`, `trashSubscriptions` and `restoreSubscriptions`.

- [ ] **Step 3: Implement schema v2 and migration**

Use a new key `ft-research:ai-rss-subscriptions:v2`, while reading v1 once for migration:

```ts
export interface RssTrashEntry {
  id: string;
  kind: "builtin" | "custom";
  previousIndex: number;
  wasPinned: boolean;
  custom?: CustomRssSubscription;
}

export interface RssSubscriptionState {
  version: 2;
  order: string[];
  pinned: string[];
  custom: CustomRssSubscription[];
  trash: RssTrashEntry[];
}
```

Move default `hidden` IDs into `trash`, retain complete custom records, remove trashed IDs from visible order/pins, and reinsert restored IDs at a clamped `previousIndex`.

- [ ] **Step 4: Run state tests**

Run: `node --test frontend/tests/ai-rss-subscriptions.test.mjs`

Expected: migration, trash and restoration tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/rssSubscriptions.ts frontend/tests/ai-rss-subscriptions.test.mjs
git commit -m "feat: add recoverable RSS subscription trash"
```

### Task 3: Typed refresh messages in the AI news page

**Files:**
- Modify: `frontend/src/lib/rssRefresh.ts`
- Modify: `frontend/src/pages/AINews.tsx`
- Modify: `frontend/tests/rss-refresh.test.mjs`
- Modify: `frontend/tests/ai-news-loading.test.mjs`

**Interfaces:**
- Consumes: refresh API outcome from Task 1.
- Produces: `RssRefreshResult { source, outcome, addedCount, retryAfter? }` delivered by `createRssRefresher`.

- [ ] **Step 1: Write failing refresh result tests**

Change the coordinator callback to receive the full result and assert that `current` is delivered unchanged. Add page contract assertions for all three Chinese messages:

```js
assert.match(page, /已是最新内容/);
assert.match(page, /已更新，共新增/);
assert.match(page, /更新未完成，当前显示最近一次成功内容/);
```

- [ ] **Step 2: Run the focused frontend tests and verify failure**

Run: `node --test frontend/tests/rss-refresh.test.mjs frontend/tests/ai-news-loading.test.mjs`

Expected: callback shape and message assertions fail.

- [ ] **Step 3: Implement typed result flow**

Replace the side-channel outcome map with:

```ts
export interface RssRefreshResult {
  source: RssSource;
  outcome: "updated" | "current" | "cached";
  addedCount: number;
  retryAfter?: number;
}
```

Map messages exclusively from `result.outcome`; reserve the generic failure message for rejected HTTP/network requests with no usable API result.

- [ ] **Step 4: Run the focused frontend tests**

Run: `node --test frontend/tests/rss-refresh.test.mjs frontend/tests/ai-news-loading.test.mjs`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/rssRefresh.ts frontend/src/pages/AINews.tsx frontend/tests/rss-refresh.test.mjs frontend/tests/ai-news-loading.test.mjs
git commit -m "fix: clarify RSS refresh results"
```

### Task 4: Batch management and recycle-bin UI

**Files:**
- Create: `frontend/src/components/ai/RssTrashDialog.tsx`
- Modify: `frontend/src/components/ai/AISubscriptionFeed.tsx`
- Modify: `frontend/tests/ai-rss-subscriptions.test.mjs`

**Interfaces:**
- Consumes: `trashSubscriptions`, `restoreSubscriptions`, `restoreAllSubscriptions` from Task 2.
- Produces: `RssTrashDialog` with selected IDs and restore callbacks.

- [ ] **Step 1: Write failing UI contract tests**

Assert source contains accessible controls and excludes permanent deletion:

```js
for (const text of ["批量管理", "移入回收站", "回收站", "恢复所选", "全部恢复"]) assert.match(feedAndTrash, new RegExp(text));
assert.match(feedAndTrash, /aria-modal="true"/);
assert.doesNotMatch(feedAndTrash, /永久删除/);
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `node --test frontend/tests/ai-rss-subscriptions.test.mjs`

Expected: missing management and trash controls.

- [ ] **Step 3: Implement management mode**

Add `managing`, `selectedIds`, `trashOpen` and `trashSelectedIds` state. Only render card checkboxes while managing. Render a fixed bottom action bar with selection count, cancel and “移入回收站”. Disable destructive action at zero selected items.

Keep “恢复默认”, but require an explicit confirmation dialog before replacing the current local order, pins, custom subscriptions and trash state.

- [ ] **Step 4: Implement restore-only dialog**

Build `RssTrashDialog` with focusable checkboxes, Escape close, overlay close, “恢复所选” and “全部恢复”. Show source names from the saved custom record or default source metadata. Do not include a permanent delete action.

- [ ] **Step 5: Run the focused test**

Run: `node --test frontend/tests/ai-rss-subscriptions.test.mjs`

Expected: all subscription UI contract tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ai/AISubscriptionFeed.tsx frontend/src/components/ai/RssTrashDialog.tsx frontend/tests/ai-rss-subscriptions.test.mjs
git commit -m "feat: add batch RSS management and recycle bin"
```

### Task 5: Smooth pointer, touch and keyboard sorting

**Files:**
- Create: `frontend/src/components/ai/RssSortableCard.tsx`
- Modify: `frontend/src/components/ai/AISubscriptionFeed.tsx`
- Modify: `frontend/tests/ai-rss-subscriptions.test.mjs`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: ordered visible sources and `moveSubscriptionTo`.
- Produces: `RssSortableCard({ source, dragDisabled, ...actions })`.

- [ ] **Step 1: Install sortable dependencies**

Run from `frontend`: `npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`

Expected: package manifest and lockfile contain the three dependencies.

- [ ] **Step 2: Write failing drag contract tests**

Assert the components contain `DndContext`, `SortableContext`, `PointerSensor`, `TouchSensor`, `KeyboardSensor`, `DragOverlay`, `useSortable`, `activationConstraint` and `autoScroll`, while old native `draggable` handlers are absent.

- [ ] **Step 3: Run the focused test and verify failure**

Run: `node --test frontend/tests/ai-rss-subscriptions.test.mjs`

Expected: dnd-kit contract assertions fail.

- [ ] **Step 4: Implement sensors and overlay**

Configure sensors with a small pointer distance and touch delay/tolerance:

```ts
const sensors = useSensors(
  useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
  useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
);
```

Use `DndContext` auto-scroll, a `DragOverlay`, vertical list sorting, and `arrayMove`/`moveSubscriptionTo` only in `onDragEnd`.

- [ ] **Step 5: Implement drag activation boundaries**

Attach sortable listeners to the card shell/header activation surface. Add `data-no-drag` to links, article summaries, buttons, inputs and checkboxes; stop pointer activation from those elements. Preserve explicit up/down controls as keyboard/fallback sorting.

- [ ] **Step 6: Run focused tests and production build**

Run: `npm test`

Run: `npm run build`

Expected: all frontend tests pass and Vite production build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/ai/AISubscriptionFeed.tsx frontend/src/components/ai/RssSortableCard.tsx frontend/tests/ai-rss-subscriptions.test.mjs
git commit -m "feat: add touch-friendly RSS card sorting"
```

### Task 6: RSS regression and browser acceptance

**Files:**
- Modify only if a failing acceptance test exposes a defect in the files above.

**Interfaces:**
- Consumes: completed Tasks 1-5.

- [ ] **Step 1: Run the complete backend suite**

Run: `python -m pytest backend/tests -q -p no:cacheprovider`

Expected: all backend tests pass.

- [ ] **Step 2: Run complete frontend verification**

Run from `frontend`: `npm test`

Run from `frontend`: `npm run build`

Expected: tests and build pass with no TypeScript errors.

- [ ] **Step 3: Verify desktop behavior in browser**

Open `/ai/news`, refresh the same healthy source twice, and confirm the second result says “已是最新内容”. Enter batch management, move two sources to trash, restore one, reload the page and confirm state persists. Drag a card by its header and confirm news links still open normally.

- [ ] **Step 4: Verify mobile behavior in browser**

At a phone viewport, long-press a card for about 200 ms, move it toward both viewport edges and confirm automatic scrolling. Confirm tapping article links and action buttons never starts dragging.

- [ ] **Step 5: Record final verification commit if fixes were needed**

```bash
git add backend frontend
git commit -m "test: complete RSS management regression"
```
