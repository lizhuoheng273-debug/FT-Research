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
  assert.match(review, /<Link[^>]+to=\{`\/finance\/stocks\/\$\{s\.code\}`\}/);
});

test("chart requests and embedded stock data guard route changes", () => {
  assert.match(chartPanel, /requestIdRef/);
  assert.match(chartPanel, /requestIdRef\.current/);
  assert.doesNotMatch(stockData, /autoLoaded/);
  assert.match(stockData, /run\(initialCode\)/);
  assert.match(detail, /quoteRequestIdRef/);
  assert.match(detail, /setLiveQuote\(null\)/);
});

test("stock detail relies on the embedded analysis disclaimer only once", () => {
  assert.doesNotMatch(detail, /<Disclaimer\s*\/>/);
});
