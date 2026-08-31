# A 股权威资讯与热点榜改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将金融资讯改造成至少 24 小时滚动事件库，并以可验证的 A 股影响证据生成紧要快讯、A 股热门事件榜和全球观察。

**Architecture:** 在现有快讯/RSS 规范化层之后增加来源注册表、SQLite 事件库和可注入盘面反查层；`FinancialNewsService` 负责兼容 JSON 快照和统一 API，评分纯代码完成，GLM 只缓存辅助导读/候选传导。前端继续使用既有 API 客户端，增加证据字段和新的分区。

**Tech Stack:** Python 3 标准库 `sqlite3`/`json`/`urllib`、现有 AkShare/东方财富/巨潮适配器、FastAPI、React 19、TypeScript、Node `node:test`。

**Spec:** `docs/superpowers/specs/2026-08-31-financial-news-priority-design.md`

## Global Constraints

- 不购买数据、不加入真实密钥、不虚构 API；只复用现有适配器和真实公开来源。
- 缓存和 SQLite 数据库位于 `.cache`，不进入 Git；保留 `snapshot.json`/旧 API 字段兼容。
- A 股影响分严格为实际市场反应 30、板块扩散 25、因果关系 20、权威来源 15、时效/持续发酵 10。
- 总分 `>=60` 才能进 A 股主榜，`45–59` 为候选；海外低于 45 或低置信度进入最多 5 条全球观察。
- 前端读取后端缓存，默认节奏为快讯 3 分钟、官方源 10 分钟、普通 RSS 30 分钟、前端 60 秒。

## File Map

- Create `backend/financial_news_sources.json`: 可验证来源注册表及抓取节奏元数据。
- Create `backend/source_registry.py`: 注册表加载、结构校验、来源等级和运行状态。
- Create `backend/financial_news_store.py`: SQLite schema、报道 upsert、事件/关系持久化、AI 缓存和 retention。
- Create `backend/market_impact.py`: 批量行情观察、相关股票反查、15/45/90 分钟补查和证据结构。
- Modify `backend/financial_news.py`: 接入事件库、来源等级、A 股评分、分流、GLM 30 候选限制和降级。
- Modify `backend/app.py`: 保持四个 endpoint 兼容并只读后端缓存。
- Modify `backend/tests/test_financial_news.py`: 先写后端 RED/GREEN 回归与验收场景。
- Create `backend/tests/test_financial_news_store.py`, `backend/tests/test_source_registry.py`, `backend/tests/test_market_impact.py`: 新模块单元测试。
- Modify `frontend/src/lib/api.ts`: 新增影响分、证据、传导和全球观察类型。
- Modify `frontend/src/pages/FinancialNews.tsx`, `frontend/src/pages/FinancialNewsDetail.tsx`: 展示新分区和可追溯证据。
- Modify `frontend/tests/financial-news-priority.test.mjs`: 前端契约和展示回归。

### Task 1: 来源注册表与验证

**Files:**
- Create: `backend/financial_news_sources.json`
- Create: `backend/source_registry.py`
- Test: `backend/tests/test_source_registry.py`

**Interfaces:**
- `load_registry(path: str | Path | None = None) -> dict`
- `validate_source(source: dict) -> list[str]`
- `source_tier(name: str, registry: dict | None = None) -> int`
- `registry_status(registry: dict | None = None) -> dict`

- [ ] Write tests for required fields, valid tier mapping, unsupported URLs, missing time/ownership metadata, and status counts.
- [ ] Run `python -m pytest backend/tests/test_source_registry.py -q`; confirm RED because the module and registry do not exist.
- [ ] Add the real-domain registry entries and validator; do not add an unverified endpoint as a callable fetcher.
- [ ] Run the focused tests and then existing financial-news tests; confirm GREEN.
- [ ] Commit `docs` and source-registry changes with `feat: register authoritative financial news sources`.

### Task 2: SQLite rolling event store

**Files:**
- Create: `backend/financial_news_store.py`
- Test: `backend/tests/test_financial_news_store.py`

**Interfaces:**
- `FinancialNewsStore(path: str | Path, retention_hours: int = 72)`
- `upsert_reports(reports: list[dict]) -> list[str]`
- `save_events(events: list[dict]) -> None`
- `load_reports(hours: int = 72) -> list[dict]`
- `load_events(hours: int = 72) -> list[dict]`
- `get_ai_cache(key: str) -> dict | None`, `put_ai_cache(key: str, value: dict) -> None`

- [ ] Write tests proving old reports survive a later upsert, duplicate URL/content is one report, event/report relation preserves the timeline, and retention is at least 24 hours.
- [ ] Run the focused tests and observe expected RED.
- [ ] Implement idempotent schema creation, UTC timestamp normalization, JSON columns for compatible fields, and pruning only after the configured retention window.
- [ ] Run focused tests, inspect the SQLite rows, and confirm GREEN without writing database files under version control.
- [ ] Commit `feat: persist rolling financial news events in sqlite`.

### Task 3: Deterministic A 股 impact and market evidence

**Files:**
- Create: `backend/market_impact.py`
- Modify: `backend/financial_news.py`
- Test: `backend/tests/test_market_impact.py`, `backend/tests/test_financial_news.py`

**Interfaces:**
- `MarketEvidenceProvider.observe() -> dict`
- `MarketImpactEnricher(provider: MarketEvidenceProvider | None = None)`
- `enrich_event(event: dict) -> dict`
- `a_share_impact_score(event: dict) -> tuple[int, dict[str, int], list[str]]`
- `main_board_eligible(event: dict) -> bool`

- [ ] Write separate failing tests for the 30/25/20/15/10 score breakdown, verified stock/sector evidence, confidence, official urgent qualification, single rumor exclusion, and the Mango/Nvidia/Korea scenarios.
- [ ] Run only those tests and confirm RED for missing fields and functions.
- [ ] Implement the minimal objective scorer and injected provider; derive stock codes from facts/provider output, never from event-name special cases.
- [ ] Run the focused tests and confirm GREEN; keep existing `urgency_score`/`hot_score` compatibility tests passing.
- [ ] Add default provider adapters using existing batch market/stock news/announcement/interactive-QA functions with shared TTL and no user-triggered duplicate fetches.
- [ ] Add due-time scheduling metadata for immediate, +15, +45, +90 minute checks and a safe trading-session predicate.
- [ ] Commit `feat: score verified a-share event impact`.

### Task 4: Service integration and API compatibility

**Files:**
- Modify: `backend/financial_news.py`
- Modify: `backend/app.py`
- Modify: `backend/tests/test_financial_news.py`

**Interfaces:**
- `FinancialNewsService` continues to expose `overview()`, `feed(category, source, limit)`, `event(event_id)`, `status()`.
- Overview adds `aShareHot` and `globalObservation`; event adds `aShareImpactScore`, `impactBreakdown`, `marketEvidence`, `transmissionPath`, `confidence`, `mainBoardEligible`, `candidate`, `globalObservation`, `sourceTimeline`.

- [ ] Write failing tests for store-backed refresh accumulation, JSON fallback, source outage status, no-loss early news, max five global observations, and GLM failure.
- [ ] Run focused tests and observe RED.
- [ ] Integrate store upsert/load into quick and RSS refreshes, compose events from the rolling window, preserve old snapshot keys, and return cache on source failure.
- [ ] Move AI refinement cache to content hash with a daily 30-candidate budget; validate all returned entities/numbers against facts and swallow GLM errors.
- [ ] Select urgent official events plus objective high-impact events; build A 股 hot list from `mainBoardEligible`, candidates separately, and global list from non-eligible overseas events.
- [ ] Keep endpoint paths/query parameters unchanged and ensure `status` reports intervals, database health, registry status, source states and last success times.
- [ ] Run backend financial-news tests and full non-live backend suite; commit `feat: integrate rolling financial news service`.

### Task 5: Frontend evidence presentation

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/FinancialNews.tsx`
- Modify: `frontend/src/pages/FinancialNewsDetail.tsx`
- Modify: `frontend/tests/financial-news-priority.test.mjs`

**Interfaces:**
- Keep existing `FinancialNewsItem` fields and add optional typed impact/evidence fields so old snapshots render.
- Keep `api.financialNewsOverview`, `api.financialNewsFeed`, `api.financialNewsEvent`, `api.financialNewsStatus` unchanged.

- [ ] Add failing static contract tests for “A股热门事件榜”, “全球观察”, score breakdown, transmission path, market evidence, independent source timeline, and update time.
- [ ] Run the focused frontend test and observe RED.
- [ ] Add typed fields and render the new sections; show empty/degraded states and mark all computed/AI labels clearly.
- [ ] Add details for catalyst → industry → board → stocks → evidence, confidence and source timeline, preserving real original links.
- [ ] Run `npm test` and `npm run build`; confirm GREEN and no TypeScript errors.
- [ ] Commit `feat: show a-share impact evidence in financial news ui`.

### Task 6: Full verification, independent review, and delivery

**Files:**
- Modify only files required by review findings.
- Test: all existing backend/frontend suites and production build.

- [ ] Run `python -m pytest backend/tests -q`, record live-upstream failures separately from deterministic failures.
- [ ] Run `npm test`, `npm run build`, and `npx tsc -b` (or the project-equivalent TypeScript check) from `frontend`.
- [ ] Inspect `git diff --check`, `git status --short`, schema/cache ignore rules, and the complete diff against `afd648f`.
- [ ] Dispatch an independent code reviewer with the requirements, base SHA `afd648f`, and final HEAD SHA; fix every critical/important finding and rerun affected tests.
- [ ] Verify no keys, generated caches, fixture data pretending to be live, or unrelated files entered the diff.
- [ ] Commit final fixes, push `codex/financial-news-priority`, and report commit SHA, test evidence, upstream limitations, and an available preview/acceptance URL if one exists.

## Plan self-review

- Source tiers, stability/time/ownership/compliance checks: Task 1.
- 24-hour rolling persistence and JSON compatibility: Task 2 and Task 4.
- Generic盘面→股票→新闻/公告/互动易→事件链 and scheduled rechecks: Task 3.
- Event/report separation, repost handling and timeline: Task 2.
- Exact 100-point score, thresholds, confidence and global observation: Task 3 and Task 4.
- GLM boundary, content-hash cache and 30-candidate budget: Task 4.
- Four compatible endpoints, frontend sections and evidence: Tasks 4–5.
- All requested acceptance scenarios and full verification: Tasks 3, 4 and 6.
- No placeholders or unresolved TODOs are used in the implementation steps; each step names the expected command or interface.

