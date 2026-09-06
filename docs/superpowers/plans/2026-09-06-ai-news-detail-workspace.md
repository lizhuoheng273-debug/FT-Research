# AI News Detail Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AI hotspot details render useful content without false unavailable flashes and route story follow-up into the full AI workspace.

**Architecture:** Story selection and fetch recovery move into focused pure helpers so matching, retry and cancellation can be tested without a browser framework. The detail page renders explicit loading, fallback, loaded and terminal-error states. The existing AI conversation workspace accepts an `eventId`, loads story-specific context, and preserves the source route on return.

**Tech Stack:** React 19, TypeScript, React Router, FastAPI proxy endpoints, Node test runner, Vite

**Spec:** `docs/superpowers/specs/2026-09-06-rss-and-ai-detail-ux-design.md`

## Global Constraints

- Never render “详情暂不可用” before the initial request has completed.
- Existing hotspot title, summary, source and original link remain visible during retries.
- Retry transient failures twice and cancel stale requests when the story changes or the page unmounts.
- AI follow-up must use the existing full conversation workspace, not the compact side panel.
- Only the Debate page risk notice is shortened; all other disclaimer usages remain unchanged.
- Use test-driven development and commit after every independently passing task.

## File Structure

- `frontend/src/lib/aiNewsStory.ts`: story ID extraction, fallback matching and retrying fetch helper.
- `frontend/src/pages/AINews.tsx`: selects the strongest fallback and initiates prefetch.
- `frontend/src/components/ai/AIHotFeed.tsx`: exposes hover/focus/touch prefetch callbacks.
- `frontend/src/pages/AINewsDetail.tsx`: stable loading, fallback and terminal-error rendering.
- `frontend/src/lib/financeAi.ts`: serializes `eventId` for AI news workspace routes.
- `frontend/src/pages/AiConversationWorkspace.tsx`: loads and labels story-specific context.
- `frontend/src/components/ui/Disclaimer.tsx`: explicit full/compact/debate copy variants.
- `frontend/src/pages/Debate.tsx`: opts into the debate-only variant.
- `frontend/tests/ai-news-story.test.mjs`: executable helper behavior tests.
- `frontend/tests/ft-hot-news.test.mjs`: detail and prefetch UI contracts.
- `frontend/tests/finance-ai-workspace.test.mjs`: route/context contracts for the shared workspace path helpers.
- `frontend/tests/disclaimer.test.mjs`: page-specific disclaimer copy.

---

### Task 1: Story identity, fallback selection and resilient loader

**Files:**
- Create: `frontend/src/lib/aiNewsStory.ts`
- Create: `frontend/tests/ai-news-story.test.mjs`

**Interfaces:**
- Produces: `storyPublicId(topic, item?): string`
- Produces: `findStoryFallback(topic, items): HotFeedItem | undefined`
- Produces: `loadAiNewsStory(storyId, { signal, fetcher, retries, retryDelayMs }): Promise<Story>`

- [ ] **Step 1: Write failing pure-helper tests**

Transpile the new TypeScript module and test link ID precedence, title/link fallback matching, two retries, no retry for abort, and rejection after the third total attempt:

```js
assert.equal(api.storyPublicId({ id: "topic", links: { story: "https://x/stories/public-1" } }), "public-1");
assert.equal(api.findStoryFallback({ id: "topic", title: "  同一 新闻 " }, [{ id: "item", title: "同一新闻", summary: "摘要" }]).summary, "摘要");
let calls = 0;
const story = await api.loadAiNewsStory("public-1", {
  fetcher: async () => (++calls < 3 ? Promise.reject(new Error("gateway")) : { story: { title: "成功" } }),
  retries: 2, retryDelayMs: 0,
});
assert.equal(calls, 3);
assert.equal(story.title, "成功");
```

- [ ] **Step 2: Run the test and verify failure**

Run: `node --test frontend/tests/ai-news-story.test.mjs`

Expected: module or exported helpers do not exist.

- [ ] **Step 3: Implement pure matching and retry helpers**

Normalize titles by trimming whitespace and punctuation for comparison. Match in this order: story link public ID, original link, exact item/topic ID, normalized title. Implement abort-aware retry with total attempts `retries + 1` and injectable delay for deterministic tests.

- [ ] **Step 4: Run the helper tests**

Run: `node --test frontend/tests/ai-news-story.test.mjs`

Expected: all identity, matching, retry and abort tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/aiNewsStory.ts frontend/tests/ai-news-story.test.mjs
git commit -m "feat: add resilient AI news story loading"
```

### Task 2: Prefetch and stronger detail fallback

**Files:**
- Modify: `frontend/src/pages/AINews.tsx`
- Modify: `frontend/src/components/ai/AIHotFeed.tsx`
- Modify: `frontend/tests/ft-hot-news.test.mjs`

**Interfaces:**
- Consumes: `storyPublicId`, `findStoryFallback`, `loadAiNewsStory` from Task 1.
- Produces: optional `onPrefetchStory(topic, item?)` callback on `AIHotFeed`.

- [ ] **Step 1: Write failing prefetch and fallback contract tests**

Assert that `AIHotFeed` invokes the supplied callback from `onMouseEnter`, `onFocus` and `onTouchStart`, and that `AINews.openStory` uses `findStoryFallback` rather than `itemById.get(topic.id)` alone.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `node --test frontend/tests/ft-hot-news.test.mjs`

Expected: prefetch callback and helper usage are absent.

- [ ] **Step 3: Implement bounded story prefetch**

Keep a module- or page-level `Map<string, Promise<Story>>`. Prefetch only the interacted story, deduplicate by public ID, and clear rejected entries so a later click can retry. Do not prefetch all ten hotspots.

- [ ] **Step 4: Pass complete route fallback**

Build fallback from the matched item plus topic fields, including `title`, `summary`, `reason`, `category`, `score`, `source`, `publishedAt`, `links.original` and `links.story`. Include the prefetch promise result in an in-memory cache read by the detail loader; do not place full story bodies in the URL.

- [ ] **Step 5: Run the focused test**

Run: `node --test frontend/tests/ft-hot-news.test.mjs`

Expected: all hotspot and prefetch contracts pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AINews.tsx frontend/src/components/ai/AIHotFeed.tsx frontend/tests/ft-hot-news.test.mjs
git commit -m "feat: prefetch AI hotspot details"
```

### Task 3: Stable AI detail loading and final error recovery

**Files:**
- Modify: `frontend/src/pages/AINewsDetail.tsx`
- Modify: `frontend/tests/ft-hot-news.test.mjs`
- Modify: `frontend/tests/ai-news-story.test.mjs`

**Interfaces:**
- Consumes: resilient loader and prefetched cache from Tasks 1-2.
- Produces: explicit `loading`, `fallback`, `loaded`, and `failed` UI states.

- [ ] **Step 1: Write failing detail-state contract tests**

Assert the source uses an `AbortController`, cleanup abort, loading skeleton labels, final retry action, original-link fallback, and does not assign “详情暂不可用” to `digest` during loading:

```js
assert.match(detail, /AbortController/);
assert.match(detail, /animate-pulse/);
assert.match(detail, /完整详情暂时未加载成功/);
assert.doesNotMatch(detail, /const digest\s*=.*详情暂不可用/);
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `node --test frontend/tests/ft-hot-news.test.mjs frontend/tests/ai-news-story.test.mjs`

Expected: stable-state assertions fail.

- [ ] **Step 3: Implement cancellable loading**

Create an `AbortController` per `storyId`; abort it in effect cleanup. Consume a completed prefetch first, otherwise call `loadAiNewsStory` with two retries. Ignore abort errors and prevent stale responses from setting state.

- [ ] **Step 4: Implement visual states**

While loading, show title/fallback summary if present and skeleton blocks for missing content. After terminal failure, keep fallback content and show “完整详情暂时未加载成功” with “重新加载” and “查看原文”. If neither story nor fallback summary exists, render the explicit error card instead of invented digest text.

- [ ] **Step 5: Run focused tests**

Run: `node --test frontend/tests/ft-hot-news.test.mjs frontend/tests/ai-news-story.test.mjs`

Expected: detail-state tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AINewsDetail.tsx frontend/tests/ft-hot-news.test.mjs frontend/tests/ai-news-story.test.mjs
git commit -m "fix: stabilize AI hotspot detail loading"
```

### Task 4: Route hotspot follow-up into the full AI workspace

**Files:**
- Modify: `frontend/src/lib/financeAi.ts`
- Modify: `frontend/src/pages/AINewsDetail.tsx`
- Modify: `frontend/src/pages/AiConversationWorkspace.tsx`
- Modify: `frontend/tests/finance-ai-workspace.test.mjs`
- Modify: `frontend/tests/ft-hot-news.test.mjs`

**Interfaces:**
- Produces: `buildAiWorkspacePath("ai-news", { eventId })` serializes `eventId`.
- Produces: AI news conversation key `ai:ai-news:<eventId || "latest">`.

- [ ] **Step 1: Write failing route and context tests**

Add executable/path contract assertions:

```js
assert.equal(buildAiWorkspacePath("ai-news", { eventId: "story-1" }), "/ai/conversations?source=ai-news&eventId=story-1");
assert.match(detail, /workspaceSource="ai-news"/);
assert.match(detail, /workspaceEventId=\{storyId\}/);
assert.match(workspace, /\/ai\/news\/stories\/\$\{eventId\}/);
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `node --test frontend/tests/finance-ai-workspace.test.mjs frontend/tests/ft-hot-news.test.mjs`

Expected: `eventId` is omitted and the detail still opens the compact panel.

- [ ] **Step 3: Serialize and consume event identity**

Allow `buildAiWorkspacePath` to append `eventId` for `ai-news`. Read it in `AiConversationWorkspace`, load `/ai/news/stories/${eventId}`, and build context containing title, digest, latest progress, source reports and original links.

- [ ] **Step 4: Preserve conversation and return identity**

Use `conversationKey = ai:ai-news:${eventId || "latest"}` and source metadata `{ type: "ai-news", eventId }`. Preserve `location.state.from` so Back returns to the originating story URL.

- [ ] **Step 5: Switch the detail button to workspace mode**

Render:

```tsx
<AskAiButton
  context={context}
  workspaceSource="ai-news"
  workspaceEventId={storyId}
  label="AI 摘要与追问"
  suggestions={["这件事最值得关注的影响是什么？", "帮我梳理这件事的时间线"]}
/>
```

- [ ] **Step 6: Run focused tests and build**

Run: `node --test frontend/tests/finance-ai-workspace.test.mjs frontend/tests/ft-hot-news.test.mjs`

Run: `npm run build`

Expected: tests pass and TypeScript accepts the extended source metadata.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/financeAi.ts frontend/src/pages/AINewsDetail.tsx frontend/src/pages/AiConversationWorkspace.tsx frontend/tests/finance-ai-workspace.test.mjs frontend/tests/ft-hot-news.test.mjs
git commit -m "feat: open hotspot follow-up in AI workspace"
```

### Task 5: Debate-only concise disclaimer

**Files:**
- Modify: `frontend/src/components/ui/Disclaimer.tsx`
- Modify: `frontend/src/pages/Debate.tsx`
- Create: `frontend/tests/disclaimer.test.mjs`

**Interfaces:**
- Produces: `Disclaimer({ variant?: "full" | "compact" | "debate" })` while preserving `compact` compatibility until all callers are migrated.

- [ ] **Step 1: Write failing page-specific copy tests**

```js
assert.match(debate, /<Disclaimer variant="debate"/);
assert.match(disclaimer, /不构成投资建议。/);
assert.match(disclaimer, /variant === "debate"/);
assert.match(disclaimer, /请自行核实并独立决策，风险自担/);
```

The final assertion confirms the full variant still contains existing copy.

- [ ] **Step 2: Run the test and verify failure**

Run: `node --test frontend/tests/disclaimer.test.mjs`

Expected: debate variant is missing.

- [ ] **Step 3: Implement the explicit variant**

For `variant="debate"`, render the existing bordered disclaimer presentation but end its sentence exactly after `<b>不构成投资建议</b>。`. Leave the full and compact outputs unchanged.

- [ ] **Step 4: Opt in only from Debate**

Change `frontend/src/pages/Debate.tsx` from `<Disclaimer />` to `<Disclaimer variant="debate" />`.

- [ ] **Step 5: Run the focused test**

Run: `node --test frontend/tests/disclaimer.test.mjs`

Expected: debate and full-copy preservation assertions pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/Disclaimer.tsx frontend/src/pages/Debate.tsx frontend/tests/disclaimer.test.mjs
git commit -m "fix: shorten debate risk notice"
```

### Task 6: AI detail regression and browser acceptance

**Files:**
- Modify only if a failing acceptance test exposes a defect in Tasks 1-5.

**Interfaces:**
- Consumes: completed story and workspace changes.

- [ ] **Step 1: Run all frontend tests**

Run from `frontend`: `npm test`

Expected: complete Node test suite passes.

- [ ] **Step 2: Run the production build**

Run from `frontend`: `npm run build`

Expected: TypeScript and Vite build succeed.

- [ ] **Step 3: Verify normal and slow-network detail loading**

Open an AI hotspot story normally and with network throttling. Confirm no unavailable message flashes, fallback summary remains readable, skeleton appears only where content is missing, and complete detail replaces it without layout breakage.

- [ ] **Step 4: Verify terminal recovery**

Temporarily simulate an unavailable story endpoint. Confirm two automatic retries, retained fallback content, working manual reload, and a usable original-article link.

- [ ] **Step 5: Verify full AI workspace navigation**

Click “AI 摘要与追问”, confirm the full workspace opens with the selected story named in the header/context, then return and confirm the same detail page is restored.

- [ ] **Step 6: Verify disclaimer isolation**

Open Debate and one other page using `Disclaimer`. Confirm Debate ends at “不构成投资建议。” and the other page retains the complete notice.

- [ ] **Step 7: Commit acceptance fixes if needed**

```bash
git add frontend
git commit -m "test: complete AI detail workspace regression"
```
