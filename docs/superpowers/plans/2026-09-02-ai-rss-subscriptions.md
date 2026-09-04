# AI RSS Subscription Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AI 热点榜下提供安全、可恢复、本地个性化的国内科技媒体 RSS 订阅流。

**Architecture:** `backend/rss.py` 负责 URL 安全、RSS/Atom 解析、媒体快照和文件缓存；`newsradar.py` 继续提供 `/api/radar` 兼容响应并复用逐媒体缓存。前端将热点榜和媒体卡片拆成独立组件，`rssSubscriptions.ts` 负责本地配置，`AISubscriptionFeed.tsx` 负责搜索、排序、添加和卡片交互。

**Tech Stack:** Python 标准库、FastAPI、pytest；React 19、TypeScript、Tailwind、Node test runner。

**Spec:** `docs/superpowers/specs/2026-09-02-ai-rss-subscriptions-design.md`

## Global Constraints

- 只修改 `FT-Research` 内层仓库；保留并行任务的 `frontend/package.json` 与 `frontend/vite.config.ts` 未提交改动。
- `/api/radar` 继续可用；RSS 缓存只放 `backend/.cache`，不提交。
- 不把用户订阅关系写入后端；不调用 GLM 批量生成摘要，不复制 RSS 正文。
- 所有 URL 抓取都执行 HTTP/HTTPS、凭据、内网和每次重定向安全校验，并限制资源。
- 每个生产行为先有一个会失败的测试，再实现最小代码并运行相关回归。

## Task 1: RSS parsing, safe fetching, and source cache

**Files:** create `backend/rss.py`; create `backend/tests/test_rss.py`.

- [ ] Add failing tests for RSS and Atom parsing, HTML-to-text summaries, safe URL rejection, redirect revalidation, cache stale fallback and three-item ordering.
- [ ] Run `python -m pytest backend/tests/test_rss.py -v` and confirm missing module/behavior failures.
- [ ] Implement `RssItem`, `RssSource`, `parse_feed`, `validate_public_url`, bounded redirect handler, SHA-256 cache, and `RssCatalog` with twelve fixed domestic sources.
- [ ] Run focused tests until green, then run the existing radar tests.

## Task 2: RSS API and radar compatibility

**Files:** modify `backend/app.py`, `backend/newsradar.py`; create `backend/tests/test_rss_api.py`; modify `backend/tests/test_api.py` only for compatibility coverage.

- [ ] Add failing API tests for `GET /api/ai/rss/sources`, `POST /api/ai/rss/resolve`, validation errors, custom cache isolation, and `/api/radar` retaining industries plus per-source snapshots.
- [ ] Implement read-only source endpoint and resolve endpoint with no user persistence; connect the 30-minute background refresh to the catalog.
- [ ] Extend radar cache with `sources` and `sourceHealth` while preserving existing industry fields and stale behavior.
- [ ] Run `python -m pytest backend/tests/test_rss.py backend/tests/test_rss_api.py backend/tests/test_api.py -v`.

## Task 3: Local subscription state and media feed UI

**Files:** create `frontend/src/lib/rssSubscriptions.ts`; create `frontend/src/components/ai/AISubscriptionFeed.tsx`; modify `frontend/src/pages/AINews.tsx`; modify `frontend/tests/ft-hot-news.test.mjs`; create `frontend/tests/ai-rss-subscriptions.test.mjs`.

- [ ] Add failing source-level tests for removed 精选事件, domestic default ordering, three items per card, original URL links, localStorage state, search scroll/highlight, keyboard/pointer ordering, pin/hide/restore, custom add/delete.
- [ ] Implement typed local state reducer and `AISubscriptionFeed` with accessible controls and no category labels.
- [ ] Replace only the news page's lower event list; keep `AIHotFeed` unchanged for `AIDaily`.
- [ ] Run focused then full frontend tests.

## Task 4: Final verification and boundary commit

**Files:** only regression fixes discovered by tests.

- [ ] Inspect `git diff`, `git status`, and ensure no `.cache` or user local data is staged.
- [ ] Run `python -m pytest -m "not live"` from `backend`.
- [ ] Run `npm test`, `npx tsc -b`, and `npm run build` from `frontend`.
- [ ] Review diff for XSS/SSRF, AI Daily regression and known parallel uncommitted config changes.
- [ ] Commit only this task's files with `feat: add AI RSS subscription feed` and report the hash without pushing.
