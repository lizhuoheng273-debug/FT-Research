# Market Review and Finance AI Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复指数图表，建立真实数据驱动的每日市场复盘快照与盘后简述，并将金融 AI 入口统一到可恢复上下文的全屏工作台。

**Architecture:** 后端以 `market_review.py` 作为独立聚合边界，复用现有 `market.py`、`astock.py`、`market_chart.py` 和 `gstock.py` 的真实数据能力，为所有页面和 AI 上下文提供一个带来源、stale、partial 语义的快照。前端新增 typed API contract、复盘展示组件和统一 Finance AI workspace；旧接口及旧个股 AI 路由保持兼容。盘后简述在独立服务中消费快照，调度只负责交易日/时间门槛和幂等。

**Tech Stack:** Python 3.12、FastAPI、pytest、requests/AKShare 现有适配；React 19、TypeScript、React Router、Tailwind、Node test runner、Vite。

**Spec:** `docs/superpowers/specs/2026-09-02-market-review-ai-workbench-design.md`

## Global Constraints

- 只修改 `FT-Research` 内层仓库的 `codex/ft-research-v1-v2` 分支，不修改外层“咨询平台”仓库。
- 保留已有用户改动；每个阶段先写失败测试、确认失败、实现、确认通过，再提交一个可恢复 Git commit。
- 生产行情只能来自真实上游或最近真实缓存；fixture 只能存在于测试，不能成为运行时回退。
- 指数 `intraday`/`five_day` 不计算或绘制 VWAP；股票 VWAP 保持现有语义。
- 沪深成交额只统计上交所和深交所股票市场，排除北交所、基金、债券、回购，并保证今日/上一交易日同口径。
- AI 继续使用现有 `/api/chat` NDJSON 流、GLM 配置和 `useAiChatSession`；不把大段上下文写进 URL。
- 最终必须运行后端完整离线测试、前端完整测试、TypeScript/生产构建和本地浏览器验收；未完成且未验证不得推送。

## File Map

- Modify `backend/market_chart.py`: 可空均价、指数分时/五日真实价格线、五个交易日筛选。
- Create `backend/market_review.py`: 快照契约、数据源适配、来源状态、组件缓存和统一聚合。
- Create `backend/market_review_brief.py`: 盘后简述 prompt、200 字约束、快照哈希和成功缓存。
- Modify `backend/app.py`: 注册 `/api/market/review`，接入盘后调度生命周期，保留旧路由。
- Modify `backend/astock.py` only if official exchange turnover adapters need a narrow normalization helper; do not alter unrelated stock APIs.
- Modify or create `backend/tests/test_market_chart.py`, `backend/tests/test_market_review.py`, `backend/tests/test_market_review_brief.py`, `backend/tests/test_api.py`.
- Modify `frontend/src/lib/api.ts`: `ChartPoint.average`、`MarketReview`、复盘 API 和 global-index status 类型。
- Modify `frontend/src/components/market/MarketChart.tsx`: close-only index series and nullable average rendering.
- Modify `frontend/src/pages/DailyReview.tsx`: unified snapshot page layout and two modal launchers.
- Create focused frontend components under `frontend/src/components/market/`: `MarketReviewModal.tsx` and `MarketReviewSummary.tsx` if the current page exceeds one responsibility.
- Modify `frontend/src/pages/FinancialNews.tsx`: move global indices strip below title and above urgent feed.
- Create `frontend/src/pages/FinanceAiWorkspace.tsx`: source-aware full-screen workspace and context reload.
- Modify `frontend/src/pages/StockAiWorkspace.tsx`, `frontend/src/pages/FinancialNewsDetail.tsx`, `frontend/src/pages/IndexDetail.tsx`, `frontend/src/pages/SectorDetail.tsx`, `frontend/src/pages/Watchlist.tsx`, `frontend/src/pages/StockData.tsx`, `frontend/src/pages/StockDetail.tsx`: route all relevant Ask AI actions to the shared workspace while preserving page-local AI drawer behavior.
- Modify `frontend/src/router.tsx` and `frontend/src/components/layout/Layout.tsx`: register workspace and workspace chrome behavior.
- Modify `frontend/tests/ft-stock-detail.test.mjs`, `frontend/tests/financial-news-priority.test.mjs`, `frontend/tests/research-framework.test.mjs`, `frontend/tests/stock-ai-workspace.test.mjs`; create `frontend/tests/market-review.test.mjs` and `frontend/tests/finance-ai-workspace.test.mjs`.

---

### Task 1: Make chart averages nullable and remove index VWAP

**Files:**
- Modify: `backend/market_chart.py` in `_point`, `_apply_intraday_vwap`, `_fetch_from_akshare`, `_aggregate`, `get_chart`.
- Modify: `frontend/src/lib/api.ts` chart types.
- Modify: `frontend/src/components/market/MarketChart.tsx` chart option construction.
- Test: `backend/tests/test_market_chart.py`, `frontend/tests/market-review.test.mjs`.

**Interfaces:**
- `ChartPoint.average: number | null`.
- Add a pure backend helper `market_chart.prepare_points(asset: str, period: str, points: list[dict]) -> list[dict]` or keep equivalent logic in `_fetch_from_akshare`; it must apply VWAP only when `asset == "stock"`.
- The front-end chart must use `average` as an optional series and never include an average series for `asset === "index"`.

- [ ] **Step 1: Write the failing tests.** Add tests with real-price-shaped index bars around 3900–4500 that assert `average is None` for `intraday` and `five_day`, while stock bars still have cumulative VWAP. Add a source-level frontend test asserting index chart options do not create an average line when the field is null.

```python
def test_index_intraday_and_five_day_points_have_no_average():
    points = [{"time": "2026-09-01T09:31", "open": 4000, "high": 4010,
               "low": 3990, "close": 4005, "average": 4002,
               "volume": 100, "amount": 400500}]
    assert all(point["average"] is None for point in
               market_chart.prepare_points("index", "intraday", points))
```

- [ ] **Step 2: Run the focused tests and verify RED.**

Run: `python -m pytest tests/test_market_chart.py -k "index_intraday_and_five_day_points_have_no_average" -v` and `npm test -- --test-name-pattern="index chart"` from `frontend`.

Expected: backend fails because index preparation still writes a numeric average; frontend fails because the current chart series does not distinguish nullable averages.

- [ ] **Step 3: Implement the minimal behavior.** Make `_point` preserve an explicitly absent average as `None`; make `prepare_points` call `_apply_intraday_vwap` only for stock and set index averages to `None` for intraday/five_day. Keep stock cumulative VWAP and historical average aggregation unchanged unless the value is null. In `MarketChart.tsx`, add the optional average series only when at least one point has a finite average and keep the close series as the index primary line.

- [ ] **Step 4: Run focused and related tests.**

Run: `python -m pytest tests/test_market_chart.py -v`; `npm test -- --test-name-pattern="chart|index"`.

Expected: all chart tests pass, including the existing stock VWAP tests and the four index adapter tests.

- [ ] **Step 5: Commit.**

```powershell
git add backend/market_chart.py backend/tests/test_market_chart.py frontend/src/lib/api.ts frontend/src/components/market/MarketChart.tsx frontend/tests/market-review.test.mjs
git commit -m "fix: keep index charts on real price scale"
```

### Task 2: Build the unified real-data market review snapshot

**Files:**
- Create: `backend/market_review.py`.
- Modify: `backend/app.py`.
- Modify: `backend/market.py` only for narrow reusable source normalization if required.
- Test: `backend/tests/test_market_review.py`, `backend/tests/test_api.py`.

**Interfaces:**
- `MarketReviewService(cache_dir: Path | None = None, now_fn: Callable[[], datetime] | None = None, source_adapters: dict | None = None)`.
- `MarketReviewService.get_review(force: bool = False) -> dict`.
- `build_breadth(up: int | None, down: int | None, limit_up: int | None, limit_down: int | None) -> dict` with only `up`, `down`, `upRatio`, `downRatio`, `limitUp`, `limitDown`.
- `build_liquidity(today_amount_yuan: int | None, previous_amount_yuan: int | None) -> dict` with `direction` in `expanded|contracted|unchanged`.
- `GET /api/market/review` returns the contract in the spec without wrapping it in a second legacy `data` envelope.

- [ ] **Step 1: Write failing contract and normalization tests.** Cover breadth with no flat field and ratios summing to 100; zero denominator returns null ratios; liquidity change and direction; official exchange rows include only Shanghai/Shenzhen stock-market totals; required-source failure yields `partial=true` and no synthetic amount; cached real snapshot returns `stale=true`.

```python
def test_breadth_exposes_no_flat_and_ratios_sum_to_100():
    result = build_breadth(600, 400, 30, 8)
    assert set(result) == {"up", "down", "upRatio", "downRatio", "limitUp", "limitDown"}
    assert result["upRatio"] + result["downRatio"] == 100
```

- [ ] **Step 2: Run the focused tests and verify RED.**

Run: `python -m pytest tests/test_market_review.py -v`.

Expected: import or contract failures because the module and endpoint do not yet exist.

- [ ] **Step 3: Implement the minimal aggregator.** Add typed normalization helpers and source status records. Use existing `astock.index_quote`, `market.get_short_term_emotion`, `market.get_turnover_top`, and `market.get_overview` through adapter functions so each component can be tested independently. Implement an official turnover adapter with explicit exchange-market filters and a common yuan unit conversion; fetch today and previous trading date through the same adapter. Cache only successful real component payloads under `backend/.cache/market-review/`, using one-minute TTL intraday and next-trading-day reuse after close. Return missing components as `None`/empty with status, never call `fixture_points`.

- [ ] **Step 4: Wire the endpoint and run focused tests.** Add FastAPI validation/error translation for `/api/market/review`, then run `python -m pytest tests/test_market_review.py tests/test_api.py -v`.

Expected: all new contract, stale/partial, cache, official-scope and endpoint compatibility tests pass.

- [ ] **Step 5: Commit.**

```powershell
git add backend/market_review.py backend/app.py backend/market.py backend/tests/test_market_review.py backend/tests/test_api.py
git commit -m "feat: add unified market review snapshot"
```

### Task 3: Replace the daily review page and add accessible market modals

**Files:**
- Modify: `frontend/src/lib/api.ts`.
- Modify: `frontend/src/pages/DailyReview.tsx`.
- Create or modify: `frontend/src/components/market/MarketReviewSummary.tsx`, `frontend/src/components/market/MarketReviewModal.tsx`.
- Modify: `frontend/tests/ft-stock-detail.test.mjs`, `frontend/tests/research-framework.test.mjs`.
- Create: `frontend/tests/market-review.test.mjs`.

**Interfaces:**
- `api.marketReview(): Promise<MarketReview>`.
- `MarketReviewSummary` renders the short emotion summary, ten-item turnover summary and status labels.
- `MarketReviewModal({ open, title, onClose, children })` handles Escape, mask click, focusable close button, `role="dialog"`, `aria-modal="true"`, desktop width and mobile full-screen classes.

- [ ] **Step 1: Write failing source-level UI tests.** Assert `DailyReview.tsx` calls `api.marketReview`, has the required section order, omits the deleted modules/flat field/full first-screen tables, renders separate short-emotion and turnover modal triggers, and displays ten summary items versus twenty modal items. Assert modal source contains Escape handling, mask, close button, focus restoration and responsive classes.

- [ ] **Step 2: Run frontend focused tests and verify RED.**

Run: `npm test -- --test-name-pattern="market review|daily review"`.

Expected: failures because the existing page performs multiple legacy requests and has no unified modal contract.

- [ ] **Step 3: Implement the typed API and page layout.** Add `MarketReview` types matching the backend contract. Rewrite page-owned loading/error state around one request, render stale/partial/final/source status, place the header/AI action, brief, four indices, width/liquidity band, two summaries, sector trend and rotation in order. Use China red-up/green-down styling and show amount delta plus percentage. Keep AI context concise and derived from the loaded snapshot.

- [ ] **Step 4: Implement and connect the modal.** Render full short-term emotion details including ladder and consecutive-stock table; render turnover top 10 in two desktop columns and top 20 in the modal. Use `navigate(`/finance/stocks/${code}`)` on a concrete turnover row. Keep modal focus reachable with keyboard and restore trigger focus on close.

- [ ] **Step 5: Run focused and full frontend tests.**

Run: `npm test -- --test-name-pattern="market review|daily review|framework"` and then `npm test`.

Expected: all existing navigation/framework tests and new layout/modal tests pass.

- [ ] **Step 6: Commit.**

```powershell
git add frontend/src/lib/api.ts frontend/src/pages/DailyReview.tsx frontend/src/components/market/MarketReviewSummary.tsx frontend/src/components/market/MarketReviewModal.tsx frontend/tests/market-review.test.mjs frontend/tests/ft-stock-detail.test.mjs frontend/tests/research-framework.test.mjs
git commit -m "feat: redesign daily market review"
```

### Task 4: Move global market strip to financial news

**Files:**
- Modify: `frontend/src/pages/FinancialNews.tsx`.
- Modify: `frontend/src/pages/DailyReview.tsx` if any global request remains.
- Modify: `frontend/tests/financial-news-priority.test.mjs`, `frontend/tests/market-review.test.mjs`.

- [ ] **Step 1: Write failing tests.** Assert the global-index hook/request is absent from DailyReview and present under the FinancialNews title before the urgent feed, with name, region, price, change percentage, update time and stale status. Assert the news feed remains rendered when global data fails.

- [ ] **Step 2: Run focused tests and verify RED.**

Run: `npm test -- --test-name-pattern="global market|financial news"`.

Expected: current placement/absence assertions fail.

- [ ] **Step 3: Implement the move and failure isolation.** Reuse the existing `api.globalIndices` contract; add explicit `stale`/updated rendering if the backend payload provides it. Keep `globalObservation` events in the news page. Load global indices independently from overview/feed state and render a compact unavailable state without preventing the urgent/feed content.

- [ ] **Step 4: Run tests and commit.**

Run: `npm test -- --test-name-pattern="global market|financial news"` and `npm test`.

```powershell
git add frontend/src/pages/FinancialNews.tsx frontend/src/pages/DailyReview.tsx frontend/tests/financial-news-priority.test.mjs frontend/tests/market-review.test.mjs
git commit -m "feat: place global market strip on finance news"
```

### Task 5: Add the unified Finance AI workspace and migrate entries

**Files:**
- Create: `frontend/src/pages/FinanceAiWorkspace.tsx`.
- Modify: `frontend/src/router.tsx`, `frontend/src/components/layout/Layout.tsx`.
- Modify: `frontend/src/pages/StockAiWorkspace.tsx`, `frontend/src/pages/DailyReview.tsx`, `frontend/src/pages/FinancialNews.tsx`, `frontend/src/pages/FinancialNewsDetail.tsx`, `frontend/src/pages/IndexDetail.tsx`, `frontend/src/pages/SectorDetail.tsx`, `frontend/src/pages/Watchlist.tsx`, `frontend/src/pages/StockData.tsx`, `frontend/src/pages/StockDetail.tsx`.
- Modify: `frontend/src/components/ui/AskAiButton.tsx` only to support a shared route target without changing the existing drawer mode.
- Test: `frontend/tests/finance-ai-workspace.test.mjs`, `frontend/tests/stock-ai-workspace.test.mjs`, `frontend/tests/research-framework.test.mjs`.

**Interfaces:**
- `FinanceAiSource = "review" | "news" | "watchlist" | "index" | "stock" | "stock-panel" | "news-story"`.
- `buildFinanceAiKey(source, identifiers): string` returns the exact isolation keys in the spec.
- Workspace reads `useSearchParams`, reloads data by identifier, builds bounded context, and passes `conversationKey`, `context`, `analysisScope` to `useAiChatSession` and `AiConversation`.

- [ ] **Step 1: Write failing route, key, reload and reuse tests.** Cover `/finance/ai` query registration, all seven sources, exact key isolation, no large JSON context in URL, reuse of `AiConversation`/`useAiChatSession`, Stop/Markdown/tool-history behavior inherited from the shared component, and compatibility routing from `/finance/stocks/:code/ai`. Assert return pathname and query state are restored.

- [ ] **Step 2: Run focused tests and verify RED.**

Run: `npm test -- --test-name-pattern="finance AI workspace|stock workspace|AI entry"`.

Expected: failures because only the stock-specific workspace exists and other Ask AI buttons open the old drawer/direct flow.

- [ ] **Step 3: Implement the shared workspace shell.** Add a source parser that accepts only the seven literals, validates required identifiers, selects `analysisScope` (`market`, `index`, `sector`, `stock` or `general`), loads the source-specific API data, and renders a concise context panel plus the existing `AiConversation`. Keep full-screen responsive layout and current status/disclaimer patterns. Use `useAiChatSession` with keys `review:<date>`, `news`, `news-story:<eventId>`, `watchlist`, `index:<code>`, `stock:<code>`, `stock-panel:<code>:<panel>`.

- [ ] **Step 4: Migrate entry points and compatibility route.** Change all specified financial Ask AI actions to navigate to `/finance/ai` with identifiers and `state.from` for return. Make `/finance/stocks/:code/ai` render the same workspace with `source=stock&code=:code`. Do not change the AI news small drawer.

- [ ] **Step 5: Run focused and full frontend tests.**

Run: `npm test -- --test-name-pattern="finance AI workspace|stock workspace|research framework"` and then `npm test`.

- [ ] **Step 6: Commit.**

```powershell
git add frontend/src/pages/FinanceAiWorkspace.tsx frontend/src/router.tsx frontend/src/components/layout/Layout.tsx frontend/src/pages frontend/src/components/ui/AskAiButton.tsx frontend/tests/finance-ai-workspace.test.mjs frontend/tests/stock-ai-workspace.test.mjs frontend/tests/research-framework.test.mjs
git commit -m "feat: unify finance AI workspace routes"
```

### Task 6: Add 15:30 post-close brief, cache, and idempotent scheduling

**Files:**
- Create: `backend/market_review_brief.py`.
- Modify: `backend/app.py` and, if cleaner, create `backend/market_review_scheduler.py`.
- Modify: `backend/market_review.py` to expose stable snapshot hash and brief field merge.
- Test: `backend/tests/test_market_review_brief.py`, `backend/tests/test_market_review.py`, `backend/tests/test_api.py`.

**Interfaces:**
- `PROMPT_VERSION = "market-review-brief-v1"`.
- `brief_ready(snapshot: dict) -> bool` requires at least three major indices, up/down breadth and liquidity.
- `build_brief_prompt(snapshot: dict) -> str` separates objective data, interpretation constraints, verification conditions and data gaps.
- `generate_brief(snapshot: dict, cfg: dict, llm_call: Callable) -> dict` returns bounded text and status.
- `PostCloseReviewScheduler(service, brief_service, now_fn, trading_day_fn).run_once() -> dict` performs one due check and is safe to call repeatedly.

- [ ] **Step 1: Write failing scheduler/brief tests.** Cover non-trading day skip, before 15:30 skip, after 15:30 generation, startup catch-up, required-data gate, GLM exception/failure retaining prior success, hard 200 Chinese-character limit, required topic prompts, same date+snapshot hash+prompt version no duplicate call, and a changed snapshot allowing one new call.

```python
def test_successful_brief_is_idempotent_for_same_snapshot(tmp_path):
    calls = []
    service = make_brief_service(tmp_path, llm_call=lambda prompt: calls.append(prompt) or "指数表现与分化……")
    snapshot = complete_snapshot()
    assert service.generate(snapshot)["status"] == "generated"
    assert service.generate(snapshot)["status"] == "generated"
    assert len(calls) == 1
```

- [ ] **Step 2: Run focused tests and verify RED.**

Run: `python -m pytest tests/test_market_review_brief.py -v`.

Expected: module/import failures because no brief service or scheduler exists.

- [ ] **Step 3: Implement brief generation and persistence.** Store JSON at `backend/.cache/market-review/YYYY-MM-DD.json` with snapshot, hash, prompt version, status, text, generatedAt and error/status metadata. Call existing GLM configuration and chat transport, strip markdown if needed, hard-truncate to 200 Chinese characters without adding claims, and preserve a previous success when a new attempt fails. Make all clock logic timezone-aware Asia/Shanghai and use a small trading-day helper that excludes weekends and uses the most recent valid snapshot date.

- [ ] **Step 4: Wire lifecycle and endpoint response.** Run scheduler once after startup and on a bounded background interval, but never more than once per trading date/hash/version. Merge brief status into `/api/market/review`; do not block the HTTP request on GLM. Ensure tests can inject `now_fn`, trading-day function and `llm_call` without network.

- [ ] **Step 5: Run focused, full backend and frontend contract tests.**

Run: `python -m pytest tests/test_market_review.py tests/test_market_review_brief.py tests/test_api.py -v`; `npm test`.

- [ ] **Step 6: Commit.**

```powershell
git add backend/market_review.py backend/market_review_brief.py backend/market_review_scheduler.py backend/app.py backend/tests/test_market_review.py backend/tests/test_market_review_brief.py backend/tests/test_api.py
git commit -m "feat: schedule idempotent post-close market brief"
```

### Task 7: Full verification and browser acceptance

**Files:**
- Modify only if verification exposes a tested defect; add a regression test before any fix.
- Do not commit cache files, `.env`, generated build output or browser artifacts.

- [ ] **Step 1: Inspect the final diff and repository state.**

Run: `git status --short`; `git diff --check`; `git log --oneline -8`; verify outer repository status is unchanged except for its pre-existing untracked directories.

- [ ] **Step 2: Run complete backend offline verification.**

Run from `backend`: `python -m pytest -m "not live"`.

Expected: zero failures; record total passed, deselected and warnings.

- [ ] **Step 3: Run complete frontend, TypeScript and production build verification.**

Run from `frontend`: `npm test`; `npx tsc -b`; `npm run build`.

Expected: all tests pass, TypeScript exits 0 and Vite production build exits 0.

- [ ] **Step 4: Run local browser acceptance.** Start backend on port 8900 using the repository scripts or `python -m uvicorn app:app --app-dir backend --port 8900`, start frontend with `npm run dev -- --host 127.0.0.1`, then inspect `/finance/review`, `/finance/news`, `/finance/ai?source=review`, `/finance/ai?source=index&code=000001` and `/finance/stocks/000001/ai`. Verify the four index codes, chart scale, five real trading dates, widths/liquidity, modal keyboard behavior, 10/20 turnover rows, global strip location, workspace refresh/return and streaming stop.

- [ ] **Step 5: Commit only any verification-driven regression fixes.** For each defect, add a failing test, run it, fix, run the relevant suite, then commit with a focused message. Re-run the complete commands after the last fix and report exact evidence. Do not push.
