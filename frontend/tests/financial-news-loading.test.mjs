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
  publishTimeLabel: "截至 18:00 截稿",
  dateLabel: "2026 年 11 月 25 日 · 星期三",
  dayNumber: "25",
  generatedAt: "2026-11-25T10:00:00Z",
  storyCount: 4,
  lead: {
    reportKey: "rep-lead",
    storyId: "st-lead",
    milestoneCount: 4,
    reportCount: 12,
    bucket: "macro",
    sectionName: "宏观数据与政策",
    title: "央行宣布降准 0.25 个百分点",
    summary: "中国人民银行宣布下调金融机构存款准备金率 0.25 个百分点，释放约 5000 亿元长期流动性，维护年末资金面平稳。",
    sourceName: "中国人民银行",
    publishedAt: "2026-11-25T06:30:00Z",
    originalUrl: "https://www.pbc.gov.cn/",
  },
  keyPicks: [
    { reportKey: "rep-1", storyId: "st-1", sectionCode: "01", sectionName: "宏观数据与政策", title: "美联储纪要分歧加大", summary: "分歧加大" },
    { reportKey: "rep-2", storyId: "st-2", sectionCode: "02", sectionName: "市场表现", title: "A股收评：沪指放量上涨 1.4%", summary: "沪指放量上涨" },
    { reportKey: "rep-3", storyId: "st-3", sectionCode: "03", sectionName: "海外公司事件与财报", title: "英伟达三季度数据中心营收大增", summary: "数据中心营收大增" },
  ],
  sections: [
    {
      key: "macro",
      code: "01",
      name: "宏观数据与政策",
      note: "央行与财政",
      items: [{ reportKey: "rep-1", storyId: "st-1", milestoneCount: 2, reportCount: 4, bucket: "macro", title: "美联储纪要分歧加大", summary: "多位委员强调观察核心通胀走势，美债收益率走高。", sourceName: "CNBC", publishedAt: null, originalUrl: "https://cnbc.com" }],
    },
    {
      key: "market",
      code: "02",
      name: "市场表现",
      note: "中美港市场",
      items: [{ reportKey: "rep-2", storyId: "st-2", milestoneCount: 1, reportCount: 2, bucket: "market", title: "A股收评：沪指放量上涨 1.4%", summary: "三大股指集体走高，两市成交额放大至 1.8 万亿元。", sourceName: "第一财经", publishedAt: null, originalUrl: "https://yicai.com" }],
    },
    {
      key: "companies",
      code: "03",
      name: "海外公司事件与财报",
      note: "重点科技与龙头公司",
      items: [{ reportKey: "rep-3", storyId: "st-3", milestoneCount: 1, reportCount: 3, bucket: "companies", title: "英伟达三季度数据中心营收大增", summary: "英伟达三季度数据中心营收达 308 亿美元，创单季新高。", sourceName: "FT", publishedAt: null, originalUrl: "https://ft.com" }],
    },
  ],
};

test("renders AIHOT-style flat layout with lead, 3 picks, 3 thematic sections, and bottom calendar", async () => {
  let signal;
  const app = mount({
    financialDailyLatest: (_type, s) => {
      signal = s;
      return Promise.resolve(sampleEdition);
    },
    financialDailyEditions: () => Promise.resolve([{ editionKey: "2026-11-25-evening", editionDate: "2026-11-25", editionType: "evening", publishTimeLabel: "截至 18:00 截稿", leadTitle: "央行宣布降准", updatedAt: "" }]),
    financialNewsCalendar: () => Promise.resolve({ items: [{ id: "cal-1" }] }),
  });
  await flush();

  const content = app.text();
  assert.match(content, /头条/);
  assert.match(content, /今日看点/);
  assert.match(content, /宏观数据与政策/);
  assert.match(content, /市场表现/);
  assert.match(content, /海外公司事件与财报/);
  // Removed modules must NOT appear
  assert.doesNotMatch(content, /本期导读/);
  assert.doesNotMatch(content, /来源覆盖/);
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
