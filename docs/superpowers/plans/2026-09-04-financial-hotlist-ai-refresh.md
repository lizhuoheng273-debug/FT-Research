# Financial Hot-list AI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the global financial Top 5 timely while invoking AI only when new evidence can materially change the board.

**Architecture:** Quick feeds and RSS retain their 3-minute and 30-minute ingestion schedules. Deterministic normalization, financial filtering, clustering, and scoring run after every successful ingestion; a stateful AI review gate coalesces ordinary changes for five minutes, immediately admits urgent official events, enforces a ten-minute minimum interval, and performs a thirty-minute safety review. AI output remains cached by candidate-set fingerprint, while the last successful ranking remains available during model failures.

**Tech Stack:** Python/FastAPI backend, JSON/SQLite caches, React/TypeScript frontend, pytest and Node test runner.

**Spec:** Approved conversation design on 2026-09-04: event-driven AI review, 5-minute coalescing, urgent bypass, 10-minute rate limit, 30-minute safety review, 15:10 close review, and visible review timestamps.

## Global Constraints

- Quick feeds remain on a 180-second interval.
- RSS remains on a 1800-second interval.
- AI is never required for deterministic ranking or cached fallback.
- Identical candidate content must not consume another AI request.
- News links continue to open the original publisher page.
- Existing unrelated worktree changes must not be modified.

---

### Task 1: Safe quick-news headlines

**Files:**
- Modify: `backend/financial_news.py`
- Test: `backend/tests/test_financial_news.py`

**Interfaces:**
- Consumes: vendor rows accepted by `FinancialNewsService.normalize_quick_rows()`.
- Produces: concise `title` plus preserved full `summary` for content-only rows.

- [ ] Add a regression test whose content-only row contains a multi-sentence body and assert that the title is a bounded first sentence while the summary retains the body.
- [ ] Run the focused test and confirm it fails because the full body is currently used as the title.
- [ ] Add a deterministic headline extractor with punctuation-aware truncation.
- [ ] Run the focused backend test and confirm it passes.

### Task 2: AI review trigger policy and semantic editorial batch

**Files:**
- Modify: `backend/financial_news.py`
- Test: `backend/tests/test_financial_news.py`

**Interfaces:**
- Consumes: up to twenty finance-filtered clustered candidates and the persisted AI-review metadata.
- Produces: cached `displayTitle`, `aiDigest`, `impactTags`, `aiImportance`, `aiRelatedEventIds`, plus `aiReview` timestamps and status.

- [ ] Add tests for unchanged fingerprints, five-minute coalescing, ten-minute minimum interval, urgent first-review bypass, thirty-minute safety review, and a 15:10 post-close review.
- [ ] Run the focused tests and confirm the policy API is absent or returns the wrong decision.
- [ ] Implement a pure review-decision helper and persist pending/last-attempt/last-success fingerprints and timestamps.
- [ ] Add a batched AI editorial response contract that may link semantically related event IDs without fabricating sources or numbers.
- [ ] Apply accepted AI importance as a bounded secondary ordering signal while deterministic eligibility remains mandatory.
- [ ] Run focused backend tests and confirm fallback preserves deterministic output and last successful AI metadata.

### Task 3: Refresh endpoint and scheduler integration

**Files:**
- Modify: `backend/financial_news.py`
- Modify: `backend/app.py`
- Modify: `backend/route_policy.py`
- Test: `backend/tests/test_financial_news.py`
- Test: `backend/tests/test_route_policy.py`

**Interfaces:**
- Produces: `POST /api/finance/news/refresh`, returning the refreshed overview and whether AI ran, was deferred, or reused cache.

- [ ] Add failing API and route-policy tests.
- [ ] Add one serialized service method that refreshes quick news and RSS, then lets the shared review gate decide whether AI runs.
- [ ] Wire the scheduler's existing ingestion cycles through the same review policy.
- [ ] Run endpoint, policy, and scheduler tests.

### Task 4: Visible freshness and manual refresh UX

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/FinancialNews.tsx`
- Modify: `frontend/src/components/news/FinancialNewsPanels.tsx`
- Test: `frontend/tests/financial-news-panels.test.mjs`
- Test: `frontend/tests/financial-news-loading.test.mjs`

**Interfaces:**
- Consumes: `FinancialNewsOverview.aiReview` and combined refresh response.
- Produces: visible data-update, last-AI-review, and next-safety-review times; manual refresh feedback.

- [ ] Add failing render and interaction tests for review timestamps and combined refresh.
- [ ] Extend the typed API contract.
- [ ] Render concise freshness metadata in the hot-list header and make the page refresh button refresh news plus calendar.
- [ ] Run focused frontend tests and TypeScript checks.

### Task 5: Verification

**Files:**
- No production changes.

- [ ] Run all financial-news backend tests.
- [ ] Run all frontend tests.
- [ ] Run TypeScript and production build.
- [ ] Exercise the local refresh/status endpoints and verify that unchanged content does not invoke AI again.
- [ ] Review `git diff` to ensure unrelated market-review and stock-search files are untouched.
