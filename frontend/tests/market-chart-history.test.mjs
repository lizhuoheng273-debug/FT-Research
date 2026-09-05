import assert from "node:assert/strict";
import test from "node:test";

import {
  mergeHistoryPoints,
  restoreZoomWindow,
  shouldLoadFullHistory,
  visibleWindowTimes,
} from "../src/lib/marketChartHistory.ts";

const point = (time, close) => ({
  time, open: close, high: close, low: close, close, average: close, volume: 1, amount: close,
});

test("only daily-style charts request full history near the left boundary", () => {
  assert.equal(shouldLoadFullHistory("daily", 2, false, false), true);
  assert.equal(shouldLoadFullHistory("weekly", 3, false, false), true);
  assert.equal(shouldLoadFullHistory("monthly", 0, false, false), true);
  assert.equal(shouldLoadFullHistory("intraday", 0, false, false), false);
  assert.equal(shouldLoadFullHistory("daily", 2, true, false), false);
  assert.equal(shouldLoadFullHistory("daily", 2, false, true), false);
  assert.equal(shouldLoadFullHistory("daily", 8, false, false), false);
});

test("full history replaces duplicates and keeps chronological order", () => {
  const recent = [point("2026-01-03", 3), point("2026-01-04", 4)];
  const full = [point("2026-01-02", 2), point("2026-01-03", 30), point("2026-01-04", 4)];

  assert.deepEqual(mergeHistoryPoints(recent, full), [
    point("2026-01-02", 2), point("2026-01-03", 30), point("2026-01-04", 4),
  ]);
});

test("restored zoom keeps the same visible dates after older rows are prepended", () => {
  const times = ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01"];
  assert.deepEqual(restoreZoomWindow(times, "2022-01-01", "2024-01-01"), {
    startValue: 2,
    endValue: 4,
  });
});

test("zoom percentages resolve to stable visible date anchors", () => {
  const times = ["2021", "2022", "2023", "2024", "2025"];
  assert.deepEqual(visibleWindowTimes(times, 25, 75), {
    startTime: "2022",
    endTime: "2024",
  });
});
