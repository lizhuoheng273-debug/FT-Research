import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const root = new URL("../src/", import.meta.url);
const router = fs.readFileSync(new URL("router.tsx", root), "utf8");
const detail = fs.readFileSync(new URL("pages/StockDetail.tsx", root), "utf8");
const chartPanel = fs.readFileSync(new URL("components/market/MarketChart.tsx", root), "utf8");
const chart = fs.readFileSync(new URL("lib/api.ts", root), "utf8");
const watchlist = fs.readFileSync(new URL("pages/Watchlist.tsx", root), "utf8");
const review = fs.readFileSync(new URL("pages/DailyReview.tsx", root), "utf8");
const stockData = fs.readFileSync(new URL("pages/StockData.tsx", root), "utf8");
const researchTabsUrl = new URL("components/stock/StockResearchTabs.tsx", root);
const liveQuote = fs.readFileSync(new URL("hooks/useLiveStockQuote.ts", root), "utf8");

test("router exposes stock and index detail routes while preserving research entry", () => {
  assert.match(router, /\/finance\/stocks\/:code/);
  assert.match(router, /\/finance\/indices\/:code/);
  assert.match(router, /\/finance\/research/);
});

test("detail page renders chart periods and independent actions", () => {
  assert.match(chartPanel, /intraday/);
  assert.match(chartPanel, /five_day/);
  assert.match(chartPanel, /daily/);
  assert.match(chartPanel, /weekly/);
  assert.match(chartPanel, /monthly/);
  assert.match(detail, /自选/);
  assert.match(detail, /让 AI/);
});

test("frontend client uses the unified market chart endpoint", () => {
  assert.match(chart, /marketChart/);
  assert.match(chart, /\/market\/chart/);
});

test("chart period is restored from and written to the URL", () => {
  assert.match(chartPanel, /useSearchParams/);
  assert.match(chartPanel, /setSearchParams/);
  assert.match(chartPanel, /searchParams\.get\(["']period["']\)/);
});

test("watchlist and review use real links for row navigation", () => {
  assert.doesNotMatch(watchlist, /role="link"/);
  assert.match(watchlist, /<Link[^>]+to=\{`\/finance\/stocks\/\$\{c\}`\}/);
  assert.doesNotMatch(review, /role="link"/);
  assert.match(review, /to=\{`\/finance\/stocks\/\$\{stock\.code\}`\}/);
});

test("chart requests and embedded stock data guard route changes", () => {
  assert.match(chartPanel, /requestIdRef/);
  assert.match(chartPanel, /requestIdRef\.current/);
  assert.doesNotMatch(stockData, /autoLoaded/);
  assert.match(stockData, /run\(initialCode\)/);
  assert.match(liveQuote, /requestIdRef/);
  assert.match(liveQuote, /setQuote\(null\)/);
});

test("stock detail relies on the embedded analysis disclaimer only once", () => {
  assert.doesNotMatch(detail, /<Disclaimer\s*\/>/);
});

test("stock detail header only uses the independent live quote", () => {
  assert.match(detail, /liveQuote\.change_pct/);
  assert.match(detail, /实时行情暂不可用/);
  assert.doesNotMatch(detail, /data\?\.quote/);
  assert.doesNotMatch(detail, /\["涨跌"/);
  assert.doesNotMatch(detail, /amplitude_pct/);
  assert.match(liveQuote, /document\.visibilityState/);
  assert.match(liveQuote, /15_000/);
  assert.match(liveQuote, /catch\(\(\) => \{[^}]*setQuote\(null\)/s);
});

test("stock detail uses URL-backed lazy horizontal research panels", () => {
  assert.ok(fs.existsSync(researchTabsUrl));
  const tabs = fs.readFileSync(researchTabsUrl, "utf8");
  for (const label of ["资讯", "资金筹码", "公司简况", "财务估值", "事件互动"]) {
    assert.match(tabs, new RegExp(label));
  }
  assert.match(tabs, /searchParams\.get\(["']panel["']\)/);
  assert.match(tabs, /role="tablist"/);
  assert.match(tabs, /ArrowLeft|ArrowRight/);
  assert.match(tabs, /loadedPanels/);
  assert.match(detail, /<StockResearchTabs/);
  assert.match(detail, /<StockResearchTabs key=\{code\}/);
  assert.doesNotMatch(detail, /<StockData/);
});

test("company profile has a normalized client contract", () => {
  assert.match(chart, /interface CompanyProfile/);
  assert.match(chart, /registeredCapitalWan/);
  assert.match(chart, /businessScope/);
  assert.match(chart, /companyHistory/);
  assert.match(chart, /companyInfo:/);
});
