# 全球要闻与我的关注 Implementation Plan

> **For agentic workers:** 已按本计划实施并完成验证；继续修改前请先复核当前分支状态和 `docs/FINANCIAL-NEWS-HANDOFF.md`。

**Goal:** 将 `/finance/news` 收敛为“全球要闻速览”和“我的关注”两个主体区，并提供可验证、可降级、无用户组合持久化的资讯接口。

**Architecture:** 复用现有快讯、RSS、SQLite 事件库和统一 AI 工作台。全球事件使用代码规则计算重要性、权威性、时效和独立确认四维分数；关注流把浏览器自选代码映射到公司资料、个股新闻、公告和同一事件库，不触发 GLM。

**Tech Stack:** Python 标准库/SQLite/FastAPI；React 19/TypeScript/Node `node:test`。

**Global Constraints:**

- 只使用公开标题、摘要和原文链接，不绕付费墙、不新增密钥。
- 事件库保留 72 小时；最近 24 小时为主，旧事件只有实质更新才恢复活跃。
- 全球默认 10 条、最多 20 条；官方重要单来源可入选，未经证实的单一传闻排除。
- 页面刷新只读缓存；自选股仅来自浏览器，服务端不保存用户清单或组合。
- 来源运行状态必须区分 configured、enabled、last success/failure 和 cache。

## Completed tasks

- [x] Added deterministic `global_importance_score` and `globalHighlights` without an A-share evidence gate.
- [x] Preserved legacy `urgent`/`hot`/`aShareHot`/`globalObservation` fields and old endpoints.
- [x] Preserved report metadata through SQLite and prevented repost-only refreshes from changing effective event time.
- [x] Added `following_news.py`, `FinancialNewsService.following`, and `POST /api/finance/news/following` with code normalization, deduplication, evidence labels, and pagination.
- [x] Added per-source runtime health and registered the verified ECB press RSS alongside the Federal Reserve feed.
- [x] Rebuilt the finance news page around the two required sections with responsive desktop/mobile rows, safe external links, cache messaging, and stale-request guards.
- [x] Updated the unified Finance AI workspace context to include current global highlights and following items.

## Verification

- [x] `python -m pytest backend/tests -q -m 'not live'` — 290 passed, 12 deselected.
- [x] `npm test` — 95 passed.
- [x] `npm run build` — TypeScript and Vite production build passed; only the existing large-chunk advisory remains.
- [x] `git diff --check` — no whitespace errors.
- [ ] Browser automation — unavailable in this environment; static interaction contracts, responsive classes, keyboard semantics, safe links, and production build were verified instead.
