import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const daily = await readFile(new URL("../src/pages/AIDaily.tsx", import.meta.url), "utf8");
const chart = await readFile(new URL("../src/components/market/MarketChart.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/components/layout/Layout.tsx", import.meta.url), "utf8");
const aiNews = await readFile(new URL("../src/pages/AINews.tsx", import.meta.url), "utf8");
const dailyReview = await readFile(new URL("../src/pages/DailyReview.tsx", import.meta.url), "utf8");

test("AI daily manual refresh bypasses report archives and exposes busy state", () => {
  assert.match(daily, /load\(kind, period, true\)/);
  assert.match(daily, /disabled=\{loading\}/);
  assert.match(daily, /aria-busy=\{loading\}/);
  assert.match(daily, /aria-label=\{loading\s*\?\s*["']正在刷新/);
});

test("market chart manual refresh requests force mode while normal loads stay cached", () => {
  assert.match(chart, /load\(false, true\)/);
  assert.match(chart, /disabled=\{loading\}/);
  assert.match(chart, /aria-busy=\{loading\}/);
  assert.match(api, /marketChart: \(asset: "stock" \| "index", code: string, period: ChartPeriod, adjust: "qfq" \| "hfq" \| "" = "qfq", force = false\)/);
  assert.match(api, /refresh=true/);
});

test("author footer uses the personal website and confirmed email in both layouts", () => {
  assert.match(layout, /https:\/\/vincentli-website\.com\//);
  assert.match(layout, /mailto:1211798171@qq\.com/);
  assert.doesNotMatch(layout, /x\.com\/linsizhen|simonlin0423@gmail\.com|@linsizhen/);
  assert.match(layout, /个人网站/);
  assert.equal((layout.match(/href=\{WEBSITE_URL\}/g) || []).length, 3, "website links cover collapsed icon, expanded icon, and expanded label");
});

test("AI hotspot refresh prevents duplicate loads and exposes progress", () => {
  assert.match(aiNews, /disabled=\{loading \|\| rssLoading \|\| rssBulkRefreshing\}/);
  assert.match(aiNews, /aria-busy=\{loading \|\| rssLoading \|\| rssBulkRefreshing\}/);
  assert.match(aiNews, /刷新中…/);
  assert.match(aiNews, /\/ai\/rss\/refresh-all/);
  assert.match(aiNews, /rssBody\.refreshing/);
});

test("daily review index refresh prevents duplicate loads and exposes progress", () => {
  assert.match(dailyReview, /disabled=\{loading\}/);
  assert.match(dailyReview, /aria-busy=\{loading\}/);
  assert.match(dailyReview, /正在刷新大盘指数/);
});
