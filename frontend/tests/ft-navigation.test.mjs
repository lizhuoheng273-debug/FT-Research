import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const router = await readFile(new URL("../src/router.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/components/layout/Layout.tsx", import.meta.url), "utf8");
const llm = await readFile(new URL("../src/lib/llm.ts", import.meta.url), "utf8");
const settings = await readFile(new URL("../src/pages/Settings.tsx", import.meta.url), "utf8");

test("FT-Research exposes only the confirmed AI and finance navigation", () => {
  for (const path of ["/ai/news", "/ai/daily", "/finance/news", "/finance/review", "/finance/watchlist", "/finance/debate"]) {
    assert.match(router, new RegExp(path.replaceAll("/", "\\/")));
  }
  assert.match(layout, /FT-Research/);
  assert.match(layout, /多空辩论/);
  assert.doesNotMatch(layout, /label: "AI 投研"/);
  for (const hidden of ["我的持仓", "板块中心", "我的研报", "研究记录"]) {
    assert.doesNotMatch(layout, new RegExp(hidden));
  }
});

test("GLM credentials stay on the backend", () => {
  assert.match(llm, /JSON\.stringify\(\{ messages, context \}\)/);
  assert.doesNotMatch(llm, /JSON\.stringify\(\{ messages, context, llm \}\)/);
  assert.doesNotMatch(settings, /type="password" value=\{apiKey\}/);
});
