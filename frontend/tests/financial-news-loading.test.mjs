import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import ts from "typescript";

const source = await readFile(new URL("../src/pages/FinancialNews.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

const flush = () => new Promise((resolve) => setImmediate(resolve));

function mount(api, initialSearch = "") {
  const cells = [];
  const effects = [];
  const cleanups = [];
  const deadlines = new Map();
  let cursor = 0;
  let mounted = false;
  let timer = 0;
  let currentParams = new URLSearchParams(initialSearch);
  const navigated = [];

  const fakeSetTimeout = (fn) => {
    deadlines.set(++timer, fn);
    return timer;
  };
  const fakeClearTimeout = (id) => deadlines.delete(id);
  const exports = {};

  vm.runInNewContext(compiled, {
    exports,
    Error,
    AbortController,
    URLSearchParams,
    setTimeout: fakeSetTimeout,
    clearTimeout: fakeClearTimeout,
    window: { setTimeout: fakeSetTimeout, clearTimeout: fakeClearTimeout },
    require(name) {
      if (name === "react") {
        return {
          useState(initial) {
            const i = cursor++;
            if (!(i in cells)) cells[i] = typeof initial === "function" ? initial() : initial;
            return [cells[i], (v) => { cells[i] = typeof v === "function" ? v(cells[i]) : v; }];
          },
          useEffect(fn, deps) {
            const prev = effects[cursor];
            const changed = !prev || !deps || deps.some((d, idx) => d !== prev.deps?.[idx]);
            if (!mounted || changed) {
              effects[cursor] = { fn, deps };
            }
            cursor++;
          },
          useMemo(fn) {
            return fn();
          },
        };
      }
      if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
      if (name === "@/lib/api") return { api };
      if (name === "react-router-dom") {
        return {
          Link: (props) => ({ type: "Link", props }),
          useNavigate: () => (to) => navigated.push(to),
          useSearchParams: () => [
            currentParams,
            (next) => {
              currentParams = new URLSearchParams(next);
            },
          ],
        };
      }
      return new Proxy({}, { get: (_, key) => key });
    },
  });

  function render() {
    cursor = 0;
    const tree = exports.FinancialNews();
    if (!mounted) {
      mounted = true;
      for (const entry of Object.values(effects)) {
        if (entry?.fn) cleanups.push(entry.fn());
      }
    }
    return tree;
  }

  function findAll(node, pred) {
    if (Array.isArray(node)) return node.flatMap((n) => findAll(n, pred));
    if (!node || typeof node !== "object") return [];
    const hit = pred(node) ? [node] : [];
    return [...hit, ...findAll(node.props?.children, pred)];
  }

  function nodeText(node) {
    if (node == null || typeof node === "boolean") return "";
    if (Array.isArray(node)) return node.map(nodeText).join(" ");
    if (typeof node !== "object") return String(node);
    return nodeText(node.props?.children);
  }

  render();
  return {
    render,
    findAll: (pred) => findAll(render(), pred),
    text: () => nodeText(render()),
    unmount: () => cleanups.forEach((fn) => fn?.()),
    navigated,
  };
}

const sampleEdition = {
  editionKey: "2026-11-25-evening",
  editionDate: "2026-11-25",
  editionType: "evening",
  editionTag: "晚刊",
  publishTimeLabel: "18:00 定时出刊",
  dateLabel: "2026 年 11 月 25 日 · 星期三",
  dayNumber: "25",
  generatedAt: "2026-11-25T10:00:00Z",
  overview: "央行降准落地，同时海外纪要与算力资本开支成为各版面关注重点。",
  marketStrip: { title: "当日收盘客观速览", note: "交易日 2026-11-25", items: [{ name: "上证指数", value: "3386", change: "+0.84%", direction: "up" }] },
  urgentBanner: { reportKey: "rep-lead", storyId: "st-lead", title: "央行宣布降准 0.25 个百分点", sourceName: "中国人民银行", time: "11月25日 14:30" },
  lead: {
    reportKey: "rep-lead",
    storyId: "st-lead",
    milestoneCount: 4,
    reportCount: 12,
    bucket: "macro",
    sectionName: "宏观与政策",
    title: "央行宣布降准 0.25 个百分点",
    summary: "释放约 5000 亿元长期流动性。",
    tags: ["央行"],
    sourceName: "中国人民银行",
    publishedAt: "2026-11-25T06:30:00Z",
    relativeTime: "3 小时前",
    originalUrl: "https://www.pbc.gov.cn/",
  },
  keyPicks: [
    { reportKey: "rep-1", storyId: "st-1", sectionCode: "01", sectionName: "宏观与政策", title: "美联储纪要分歧加大", summary: "分歧加大" },
    { reportKey: "rep-2", storyId: "st-2", sectionCode: "02", sectionName: "国内与 A 股", title: "沪深交易所修订并购重组指引", summary: "修订指引" },
    { reportKey: "rep-3", storyId: "st-3", sectionCode: "04", sectionName: "产业与科技", title: "海外云巨头上调算力资本开支", summary: "上调开支" },
  ],
  sections: [
    {
      key: "macro",
      code: "01",
      name: "宏观与政策",
      note: "央行与财政",
      items: [{ reportKey: "rep-1", storyId: "st-1", milestoneCount: 2, reportCount: 4, bucket: "macro", title: "美联储纪要分歧加大", summary: "分歧", tags: [], sourceName: "CNBC", publishedAt: null, originalUrl: "https://cnbc.com" }],
    },
    {
      key: "china",
      code: "02",
      name: "国内与 A 股",
      note: "交易所",
      items: [{ reportKey: "rep-2", storyId: "st-2", milestoneCount: 1, reportCount: 2, bucket: "china", title: "沪深交易所修订并购重组指引", summary: "指引", tags: [], sourceName: "上交所", publishedAt: null, originalUrl: "https://sse.com.cn" }],
    },
    {
      key: "tech",
      code: "04",
      name: "产业与科技",
      note: "算力与芯片",
      items: [{ reportKey: "rep-3", storyId: "st-3", milestoneCount: 3, reportCount: 6, bucket: "tech", title: "海外云巨头上调算力资本开支", summary: "开支", tags: [], sourceName: "FT", publishedAt: null, originalUrl: "https://ft.com" }],
    },
  ],
  coverage: { activeSources: 20, totalSources: 22, rawReports: 120, trackedStories: 18, selectedCount: 4, sources: [] },
};

test("renders single lead, three section-backed picks, urgent banner, and calendar independently", async () => {
  let signal;
  const app = mount({
    financialDailyLatest: (_type, s) => {
      signal = s;
      return Promise.resolve(sampleEdition);
    },
    financialDailyEditions: () => Promise.resolve([{ editionKey: "2026-11-25-evening", editionDate: "2026-11-25", editionType: "evening", publishTimeLabel: "18:00 定时出刊", leadTitle: "央行宣布降准", updatedAt: "" }]),
    financialNewsCalendar: () => Promise.resolve({ items: [{ id: "cal-1" }] }),
  });
  await flush();

  const content = app.text();
  assert.match(content, /今日金融头条/);
  assert.match(content, /本期看点/);
  assert.match(content, /持续事件\s+·\s+4\s+个关键节点\s+\/\s+12\s+篇报道/);
  assert.equal(app.findAll((n) => n.type === "UpcomingEvents").length, 1);

  const pickLinks = app.findAll((n) => /^\/finance\/news\/story\/rep-\d/.test(n.props?.to || ""));
  assert.ok(pickLinks.length >= 3);
  app.unmount();
  assert.equal(signal.aborted, true);
});

test("refresh triggers financialDailyRefresh and financialNewsCalendarRefresh and reports completion", async () => {
  let finishDaily;
  let dailyRefreshCalls = 0;
  let calRefreshCalls = 0;
  const app = mount({
    financialDailyLatest: () => Promise.resolve(sampleEdition),
    financialDailyEditions: () => Promise.resolve([]),
    financialNewsCalendar: () => Promise.resolve({ items: [] }),
    financialDailyRefresh: () => {
      dailyRefreshCalls++;
      return new Promise((resolve) => {
        finishDaily = resolve;
      });
    },
    financialNewsCalendarRefresh: () => {
      calRefreshCalls++;
      return Promise.resolve({ outcome: "updated" });
    },
  });
  await flush();

  const refreshBtn = app.findAll((n) => n.type === "button" && n.props?.["aria-label"] === "刷新金融日报")[0];
  assert.ok(refreshBtn);
  refreshBtn.props.onClick();
  assert.equal(dailyRefreshCalls, 1);
  assert.equal(calRefreshCalls, 1);

  finishDaily(sampleEdition);
  await flush();
  assert.match(app.text(), /本期金融日报与日程已更新/);
  app.unmount();
});
