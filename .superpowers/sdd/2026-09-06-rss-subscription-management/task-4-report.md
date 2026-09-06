# Task 4 Report: Batch management and recycle-bin UI

## Status

Complete with an unrelated full-suite test-environment concern.

## Summary

- Added browser-local batch management with selection-only checkboxes, selected-count feedback, a fixed bottom action bar, and disabled zero-selection trash action.
- Added an accessible restore-only recycle-bin modal with saved custom-name/default-source fallback labels, checkbox selection, Escape and overlay close, selected restore, and restore-all actions.
- Kept single-source hide/delete operations on the Task 2 v2 trash helpers.
- Added explicit confirmation before “恢复默认” resets local order, pins, custom subscriptions, and trash.
- Preserved Task 3 `refreshingIds`, `refreshMessages`, refresh controls, and existing RSS content interactions.

## Files

- `frontend/src/components/ai/AISubscriptionFeed.tsx`
- `frontend/src/components/ai/RssTrashDialog.tsx`
- `frontend/tests/ai-rss-subscriptions.test.mjs`

## Red/green evidence

### RED

Command:

```text
node --test tests/ai-rss-subscriptions.test.mjs
```

Result: 13 passed, 1 failed. The new contract failed on the missing `批量管理` control, confirming the test was exercising the unimplemented Task 4 behavior.

### GREEN

Command:

```text
node --test tests/ai-rss-subscriptions.test.mjs
```

Result: 14 passed, 0 failed.

## Verification

- Focused frontend test: `node --test tests/ai-rss-subscriptions.test.mjs` — 14/14 passed.
- Complete frontend tests: `npm test` — 200 total, 195 passed, 5 failed in existing conversation tests because their relative esbuild aliases hit `Cannot read directory "../../../../../../..": Access is denied` and could not resolve existing `AiConversation.tsx`/`useAiChatSession.ts` files. The failures reproduce in isolation and are unrelated to Task 4.
- Production build: `npm run build` — passed; Vite emitted only the existing large-chunk warning.
- Diff hygiene: `git diff --check` — passed.

## Self-review

- Modal focus: focuses the close button on open, closes on Escape or backdrop mouse-down, and returns focus to the recycle-bin trigger.
- Zero selection: batch trash and “恢复所选” are disabled with no selection; restore-all is disabled for an empty trash.
- Empty trash: renders an explicit empty state without destructive actions.
- Custom restore metadata: labels prefer `entry.custom.name`, then loaded source metadata, then the stable source ID; Task 2 restore preserves the full custom record.
- Narrow screens: the fixed action bar wraps and batch mode adds bottom padding so the final card remains reachable.
- No permanent-delete action or label was added.

## Commit

`a76dd00 feat: add batch RSS management and recycle bin`

## Concerns

- The complete frontend suite remains non-zero because of the pre-existing Windows/esbuild access-resolution failures in five conversation tests; resolving those would be outside Task 4.
- Vite retains its existing warning about chunks larger than 500 kB.
