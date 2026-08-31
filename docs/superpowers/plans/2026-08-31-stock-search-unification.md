# FT-Research 全站股票名称搜索统一改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变后端搜索接口、数据源或现有业务持久化的前提下，为 FT-Research 的五类入口提供统一的 A 股名称/代码搜索与规范提交能力。

**Architecture:** 用 `useStockSearch` 管理查询阈值、250ms 防抖、竞态和搜索状态；用 `StockSearchInput` 管理单选输入、候选菜单和键盘/鼠标关闭行为；用 `StockBatchPicker` 管理批量选择形成的名称+代码标签。页面只接收 6 位代码并继续负责 `parseCodes()`、`addCodes()`、本地存储和业务 API 调用。

**Tech Stack:** React 19, TypeScript strict mode, Vite, Node `node:test` source-contract tests, FastAPI backend contract tests.

**Spec:** `docs/superpowers/specs/2026-08-31-stock-search-unification-design.md`

## Global Constraints

- 复用现有 `/api/stock/search`，不修改后端接口或增加数据源。
- 候选项显示名称、代码、A股；不加入拼音搜索。
- 中文 1 字、数字/英文 2 字符触发搜索，延迟 250ms，旧请求不得覆盖新结果。
- 单选入口：名称必须选择候选；完整 6 位代码可直接提交；AI 投研保留 AAPL、00700 等外围市场代码自由输入。
- 批量入口：名称选择形成待提交的名称+代码标签，可连续选择和删除；混合粘贴继续支持逗号/空格/换行；最后由原有按钮写入本地自选。
- 公共组件不写本地存储；页面继续使用 `parseCodes()` / `addCodes()`。
- 多空辩论和持仓页面继续隐藏，不恢复侧栏入口。
- 不修改行情、K线、GLM 或存储架构。

---

### Task 1: 建立可测试的搜索策略与请求状态契约

**Files:**
- Create: `frontend/src/lib/stock-search.ts`
- Test: `frontend/tests/stock-search-core.test.mjs`

**Interfaces:**
- Produces `StockSearchItem = { code: string; name: string }` and `StockSearchState` types for later components.
- Produces `isSearchTrigger(query: string): boolean`, `normalizeAStockCode(value: string): string | null`, and `mergeBatchCodes(existing: string[], incoming: StockSearchItem[]): StockSearchItem[]`.

- [ ] **Step 1: Write failing tests for query thresholds and code normalization**

  Add Node source-contract tests that require the new module to export the named helpers and encode these vectors in the source:

  ```js
  test("search threshold accepts one Chinese character and two ASCII characters", () => {
    assert.match(core, /isSearchTrigger/);
    assert.match(core, /query\.trim\(\)\.length >= 1/);
    assert.match(core, /[A-Za-z0-9].*length >= 2/);
  });

  test("normalization only returns a six digit A-share code", () => {
    assert.match(core, /normalizeAStockCode/);
    assert.match(core, /\\^\\d\{6\\\}\$/);
    assert.match(core, /return null/);
  });

  test("batch merge removes invalid and duplicate codes without changing existing order", () => {
    assert.match(core, /mergeBatchCodes/);
    assert.match(core, /new Set/);
    assert.match(core, /existing/);
  });
  ```

- [ ] **Step 2: Run the focused test and verify the expected RED failure**

  Run: `npm test -- --test-name-pattern="search threshold|normalization|batch merge"` from `frontend`.

  Expected: FAIL because `frontend/src/lib/stock-search.ts` does not exist yet.

- [ ] **Step 3: Implement the minimal pure helpers**

  Implement one-character CJK detection, two-character ASCII/number detection, trimming/uppercasing, exact six-digit A-share normalization, and stable code deduplication. Do not add pinyin or network behavior to this module.

- [ ] **Step 4: Run the focused test and verify GREEN**

  Run: `npm test -- --test-name-pattern="search threshold|normalization|batch merge"`.

  Expected: PASS with zero failures.

- [ ] **Step 5: Commit the tested search policy**

  ```bash
  git add frontend/src/lib/stock-search.ts frontend/tests/stock-search-core.test.mjs
  git commit -m "test: define stock search normalization policy"
  ```

### Task 2: Add `useStockSearch` with debounce and race protection

**Files:**
- Create: `frontend/src/hooks/useStockSearch.ts`
- Test: `frontend/tests/stock-search-hook.test.mjs`
- Modify: `frontend/src/lib/api.ts:355` only if the hook needs a typed `StockSearchResult` alias adjustment; keep the request path unchanged.

**Interfaces:**
- Consumes: `api.stockSearch(query, limit)`, `isSearchTrigger` and `StockSearchItem` from Task 1.
- Produces:
  ```ts
  interface UseStockSearchResult {
    query: string;
    results: StockSearchItem[];
    highlightedIndex: number;
    loading: boolean;
    error: string | null;
    open: boolean;
    setQuery(query: string): void;
    setHighlightedIndex(index: number): void;
    close(): void;
    clear(): void;
  }
  export function useStockSearch(initialQuery?: string, limit?: number): UseStockSearchResult;
  ```

- [ ] **Step 1: Write failing hook contract tests**

  Add source-contract tests requiring the hook to contain the exact safety behaviors:

  ```js
  test("hook debounces search by 250ms and cancels the timer on cleanup", () => {
    assert.match(hook, /setTimeout/);
    assert.match(hook, /250/);
    assert.match(hook, /clearTimeout/);
  });

  test("hook prevents stale responses from replacing newer results", () => {
    assert.match(hook, /requestIdRef/);
    assert.match(hook, /requestId === requestIdRef\.current/);
  });

  test("hook exposes loading, error, close and clear state", () => {
    for (const name of ["loading", "error", "close", "clear"]) assert.match(hook, new RegExp(name));
  });
  ```

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `npm test -- --test-name-pattern="hook debounces|stale responses|loading, error"`.

  Expected: FAIL because the hook file and its contract are absent.

- [ ] **Step 3: Implement the minimal hook**

  Use one timer ref and one monotonically increasing request id. Clear results for queries below the threshold; set loading before `api.stockSearch`; only the current request may set results/error/loading; translate failures to a short user-facing error; expose `close()` as menu-only closure and `clear()` as query/result reset.

- [ ] **Step 4: Run focused and TypeScript checks**

  Run: `npm test -- --test-name-pattern="hook debounces|stale responses|loading, error"` and `npm run build`.

  Expected: focused tests PASS and TypeScript/build exit 0.

- [ ] **Step 5: Commit the hook**

  ```bash
  git add frontend/src/hooks/useStockSearch.ts frontend/tests/stock-search-hook.test.mjs frontend/src/lib/api.ts
  git commit -m "feat: add debounced stock search hook"
  ```

### Task 3: Build the shared single-select input

**Files:**
- Create: `frontend/src/components/stock/StockSearchInput.tsx`
- Test: `frontend/tests/stock-search-input.test.mjs`

**Interfaces:**
- Consumes: `useStockSearch`, `StockSearchItem`, `normalizeAStockCode`.
- Produces:
  ```ts
  interface StockSearchInputProps {
    value: string;
    onChange(value: string): void;
    onSelect(item: StockSearchItem): void;
    onSubmitCode(code: string): void;
    placeholder?: string;
    disabled?: boolean;
    allowExternalSymbols?: boolean;
    className?: string;
  }
  export function StockSearchInput(props: StockSearchInputProps): JSX.Element;
  ```

- [ ] **Step 1: Write failing component contract tests**

  Add tests asserting the component contract contains candidate metadata and all required interaction paths:

  ```js
  test("renders A-share candidate metadata and selection callbacks", () => {
    assert.match(input, /result\.name/);
    assert.match(input, /result\.code/);
    assert.match(input, /A股/);
    assert.match(input, /onSelect/);
  });

  test("supports keyboard navigation, selection, escape and outside click", () => {
    for (const marker of ["ArrowDown", "ArrowUp", "Enter", "Escape", "mousedown", "contains"]) {
      assert.match(input, new RegExp(marker));
    }
  });

  test("submits only a complete six digit code in A-share mode", () => {
    assert.match(input, /normalizeAStockCode/);
    assert.match(input, /onSubmitCode/);
    assert.match(input, /allowExternalSymbols/);
  });
  ```

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `npm test -- --test-name-pattern="candidate metadata|keyboard navigation|complete six digit"`.

  Expected: FAIL because `StockSearchInput.tsx` does not exist.

- [ ] **Step 3: Implement the minimal input**

  Render a controlled input and menu in a relative wrapper. Highlight index starts at zero when results arrive, wraps with arrow keys, invokes `onSelect` on Enter/click, closes on Esc/outside mouse down, and clears menu state without erasing the selected business value. In non-external mode, Enter on an exact six-digit code calls `onSubmitCode`; in external mode it calls `onSubmitCode` for the existing free-form symbol path. Render explicit loading, no-results, and error states.

- [ ] **Step 4: Run focused test and build**

  Run: `npm test -- --test-name-pattern="candidate metadata|keyboard navigation|complete six digit"` and `npm run build`.

  Expected: PASS and exit 0.

- [ ] **Step 5: Commit the single-select component**

  ```bash
  git add frontend/src/components/stock/StockSearchInput.tsx frontend/tests/stock-search-input.test.mjs
  git commit -m "feat: add shared stock search input"
  ```

### Task 4: Build the shared batch picker

**Files:**
- Create: `frontend/src/components/stock/StockBatchPicker.tsx`
- Test: `frontend/tests/stock-batch-picker.test.mjs`

**Interfaces:**
- Consumes: `StockSearchInput`, `StockSearchItem`, `parseCodes`, `addCodes` via page callback.
- Produces:
  ```ts
  interface StockBatchItem { code: string; name: string }
  interface StockBatchPickerProps {
    items: StockBatchItem[];
    onItemsChange(items: StockBatchItem[]): void;
    existingCodes: string[];
    onPasteCodes(raw: string): void;
    placeholder?: string;
  }
  export function StockBatchPicker(props: StockBatchPickerProps): JSX.Element;
  ```

- [ ] **Step 1: Write failing batch tests**

  Add source-contract tests for tag creation/deletion and the required page boundary:

  ```js
  test("batch picker forms name plus code tags and supports repeated selection", () => {
    assert.match(batch, /items/);
    assert.match(batch, /item\.name/);
    assert.match(batch, /item\.code/);
    assert.match(batch, /onItemsChange/);
  });

  test("batch picker allows deleting tags and delegates raw paste to the page", () => {
    assert.match(batch, /onPasteCodes/);
    assert.match(batch, /filter/);
    assert.match(batch, /删除|移除/);
  });

  test("batch picker keeps storage outside the shared component", () => {
    assert.doesNotMatch(batch, /localStorage/);
    assert.doesNotMatch(batch, /saveWatch/);
  });
  ```

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `npm test -- --test-name-pattern="name plus code|deleting tags|storage outside"`.

  Expected: FAIL because the component is absent.

- [ ] **Step 3: Implement the minimal picker**

  Use the shared input for repeated candidate selection. On selection, ignore codes already in `existingCodes` or already tagged, append one `{ name, code }` item, and clear the input for the next selection. Render removable tags and a textarea for raw paste; invoke `onPasteCodes` only when the page's original add action is used.

- [ ] **Step 4: Run focused test and build**

  Run: `npm test -- --test-name-pattern="name plus code|deleting tags|storage outside"` and `npm run build`.

  Expected: PASS and exit 0.

- [ ] **Step 5: Commit the batch picker**

  ```bash
  git add frontend/src/components/stock/StockBatchPicker.tsx frontend/tests/stock-batch-picker.test.mjs
  git commit -m "feat: add stock batch picker"
  ```

### Task 5: Integrate AI research and the hidden debate/portfolio inputs

**Files:**
- Modify: `frontend/src/pages/StockData.tsx`
- Modify: `frontend/src/pages/Debate.tsx`
- Modify: `frontend/src/pages/Portfolio.tsx`
- Test: `frontend/tests/stock-search-pages.test.mjs`

**Interfaces:**
- Consumes: `StockSearchInput` and the existing page submission functions.
- Produces: AI research, debate, holding add, and close-position handlers receive exact six-digit A-share codes; AI research still sends non-A-share symbols to `api.globalStock`.

- [ ] **Step 1: Write failing page contract tests**

  Assert that each page imports and renders the shared input, validates/uses the normalized code in its existing business call, and that the AI page retains `globalStock` plus examples/branch support for external symbols. Assert Debate and Portfolio do not add navigation/sidebar entries.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `npm test -- --test-name-pattern="AI research|debate|holding|close-position"`.

  Expected: FAIL because the pages still use plain code-only inputs and do not import the shared component.

- [ ] **Step 3: Implement page integration**

  Replace only the relevant code input controls. In `StockData`, wire candidate selection to route to the selected A-share detail and keep exact non-six-digit values on the existing global-market path. In `Debate`, `Portfolio` holding add, and `Portfolio` close, keep current validation and API calls but source their `code` values from `onSelect`/`onSubmitCode`. Do not change hidden navigation configuration or business persistence.

- [ ] **Step 4: Run page tests and TypeScript**

  Run: `npm test -- --test-name-pattern="AI research|debate|holding|close-position"` and `npm run build`.

  Expected: PASS with no TypeScript errors.

- [ ] **Step 5: Commit single-select integrations**

  ```bash
  git add frontend/src/pages/StockData.tsx frontend/src/pages/Debate.tsx frontend/src/pages/Portfolio.tsx frontend/tests/stock-search-pages.test.mjs
  git commit -m "feat: unify single stock search entry points"
  ```

### Task 6: Integrate daily review and watchlist batch flows

**Files:**
- Modify: `frontend/src/pages/DailyReview.tsx`
- Modify: `frontend/src/pages/Watchlist.tsx`
- Test: `frontend/tests/stock-search-batch-pages.test.mjs`

**Interfaces:**
- Consumes: `StockBatchPicker`, `loadWatch`, `saveWatch`, `parseCodes`, `addCodes`, and existing `refreshWatch`/`useLiveQuotes` flows.
- Produces: both pages keep an explicit original add button; that button merges tag codes plus parsed raw codes, filters existing/duplicates/invalid values, saves once, and refreshes quotes only after the local list changes.

- [ ] **Step 1: Write failing batch page tests**

  Assert both pages import/render `StockBatchPicker`, continue importing `parseCodes`/`addCodes` or delegate to a helper that uses them, retain `saveWatch`, retain the original add button, and pass codes (not names) to quote refresh/storage.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `npm test -- --test-name-pattern="daily review|watchlist|parseCodes|addCodes"`.

  Expected: FAIL because both pages still have code-only entry controls and no pending tag state.

- [ ] **Step 3: Implement batch integration**

  Add `pendingStocks` state to each page. Candidate selection appends labels only; deleting a label changes only pending state. On the existing add button, combine pending item codes with `parseCodes(rawText)`, call `addCodes(existing, combinedRawCodes)`, filter any pending code already present, save the resulting code list once, clear pending/raw input, and refresh quotes. Keep complete-code raw paste functional even if the search endpoint fails.

- [ ] **Step 4: Run batch tests, full frontend tests and build**

  Run: `npm test -- --test-name-pattern="daily review|watchlist|parseCodes|addCodes"`, then `npm test`, then `npm run build`.

  Expected: all commands PASS with exit 0.

- [ ] **Step 5: Commit batch integrations**

  ```bash
  git add frontend/src/pages/DailyReview.tsx frontend/src/pages/Watchlist.tsx frontend/tests/stock-search-batch-pages.test.mjs
  git commit -m "feat: add stock name selection to watchlist flows"
  ```

### Task 7: Full verification and independent read-only review

**Files:**
- Modify only files identified by failing verification or Critical/Important review findings.

- [ ] **Step 1: Run the complete frontend verification set**

  From `frontend`, run `npm test`, `npm run build`, and `npx tsc -b --pretty false`.

  Expected: each exits 0; record exact test count and build output.

- [ ] **Step 2: Run backend stock-search contract tests**

  From `backend`, run `python -m pytest tests/test_stock_search.py -q`.

  Expected: all stock-search contract tests pass and no backend source files are changed.

- [ ] **Step 3: Start the local app and perform browser acceptance**

  Start the existing frontend/backend local processes using the repository scripts. Verify on desktop: DailyReview name selection → tag → add → local watch refresh; Watchlist name selection plus mixed paste → deduped list; StockData name selection and AAPL/00700 free input. Verify arrow keys, Enter, Esc, outside click, loading/no-results/error states, and that selected names submit codes.

- [ ] **Step 4: Request independent read-only review**

  Review the final diff against the design and requirements, specifically checking stale request protection, code-only business submissions, local-storage boundaries, hidden navigation, and external-symbol compatibility. Record findings by severity and fix every Critical/Important item with a regression test before continuing.

- [ ] **Step 5: Re-run all verification after review fixes**

  Re-run `npm test`, `npx tsc -b --pretty false`, `npm run build`, and `python -m pytest tests/test_stock_search.py -q`; inspect `git diff --check` and `git status --short --branch`.

- [ ] **Step 6: Commit final changes and push the requested branch**

  ```bash
  git add frontend/src frontend/tests docs/superpowers
  git commit -m "feat: unify stock name search across research flows"
  git push origin codex/ft-research-v1-v2
  git rev-parse HEAD
  ```

  Expected: push succeeds to `origin/codex/ft-research-v1-v2`; report the exact SHA, test/build results, browser acceptance status, and any external data-source failures.
