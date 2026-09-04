import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const [stockData, debate, portfolio] = await Promise.all([
  readFile(new URL("../src/pages/StockData.tsx", import.meta.url), "utf8"),
  readFile(new URL("../src/pages/Debate.tsx", import.meta.url), "utf8"),
  readFile(new URL("../src/pages/Portfolio.tsx", import.meta.url), "utf8"),
]);

test("AI research uses the shared input and preserves external market symbols", () => {
  assert.match(stockData, /StockSearchInput/);
  assert.match(stockData, /allowExternalSymbols/);
  assert.match(stockData, /globalStock/);
  assert.match(stockData, /AAPL.*00700|00700.*AAPL/s);
});

test("debate uses shared selection and submits a normalized A-share code", () => {
  assert.match(debate, /StockSearchInput/);
  assert.match(debate, /onSelect/);
  assert.doesNotMatch(debate, /navigate\(/);
  assert.match(debate, /onSubmitCode/);
  assert.match(debate, /debateStream\(c,/);
  assert.match(debate, /d\{6\}/);
  assert.match(debate, /onChange=\{changeCode\}/);
});

test("portfolio holding and close forms use shared selection without changing API calls", () => {
  assert.match(portfolio, /StockSearchInput/);
  assert.match(portfolio, /addHolding\(normalizedCode/);
  assert.match(portfolio, /closePosition\(normalizedCode/);
  assert.match(portfolio, /onSelect/);
  assert.ok(portfolio.includes("navigate(`/finance/stocks/${result.code}`)"));
  assert.match(portfolio, /onSubmitCode/);
  assert.match(portfolio, /onChange=\{setCode\}/);
  assert.match(portfolio, /onChange=\{setCCode\}/);
});
