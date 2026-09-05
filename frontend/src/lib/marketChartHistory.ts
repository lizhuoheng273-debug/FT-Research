import type { ChartPeriod, ChartPoint } from "@/lib/api";

const LONG_PERIODS = new Set<ChartPeriod>(["daily", "weekly", "monthly"]);

export function shouldLoadFullHistory(
  period: ChartPeriod,
  startPercent: number,
  historyComplete: boolean,
  loadingHistory: boolean,
) {
  return LONG_PERIODS.has(period) && startPercent <= 3 && !historyComplete && !loadingHistory;
}

export function mergeHistoryPoints(recent: ChartPoint[], full: ChartPoint[]) {
  const byTime = new Map(recent.map((item) => [item.time, item]));
  for (const item of full) byTime.set(item.time, item);
  return [...byTime.values()].sort((left, right) => left.time.localeCompare(right.time));
}

export function restoreZoomWindow(times: string[], startTime?: string, endTime?: string) {
  if (!times.length || !startTime || !endTime) return undefined;
  const startValue = times.indexOf(startTime);
  const endValue = times.indexOf(endTime);
  if (startValue < 0 || endValue < 0) return undefined;
  return { startValue, endValue };
}

export function visibleWindowTimes(times: string[], startPercent: number, endPercent: number) {
  if (!times.length) return undefined;
  const lastIndex = times.length - 1;
  const startIndex = Math.max(0, Math.min(lastIndex, Math.round(lastIndex * startPercent / 100)));
  const endIndex = Math.max(startIndex, Math.min(lastIndex, Math.round(lastIndex * endPercent / 100)));
  return { startTime: times[startIndex], endTime: times[endIndex] };
}
