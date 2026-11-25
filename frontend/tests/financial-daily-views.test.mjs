import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import ts from "typescript";

const flush = () => new Promise((resolve) => setImmediate(resolve));

function mountPage(fileRel, exportName, api, routeParams) {
  let sourceCode;
  const load = async () => {
    sourceCode = await readFile(new URL(fileRel, import.meta.url), "utf8");
    const compiled = ts.transpileModule(sourceCode, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;

    const cells = [];
    const effects = [];
    let cursor = 0;
    let mounted = false;
    const exports = {};

    vm.runInNewContext(compiled, {
      exports,
      require(name) {
        if (name === "react") {
          return {
            useState(initial) {
              const i = cursor++;
              if (!(i in cells)) cells[i] = typeof initial === "function" ? initial() : initial;
              return [cells[i], (v) => { cells[i] = typeof v === "function" ? v(cells[i]) : v; }];
            },
            useEffect(fn) {
              if (!mounted) effects.push(fn);
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
            useParams: () => routeParams,
            useNavigate: () => () => {},
            useLocation: () => ({ state: null }),
          };
        }
        return new Proxy({}, { get: (_, key) => key });
      },
    });

    function render() {
      cursor = 0;
      const tree = exports[exportName]();
      if (!mounted) {
        mounted = true;
        effects.forEach((fn) => fn());
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
    };
  };
  return load();
}

test("FinancialNewsDetail renders followups list and full-event navigation link", async () => {
  const page = await mountPage(
    "../src/pages/FinancialNewsDetail.tsx",
    "FinancialNewsDetail",
    {
      financialNewsReportDetail: () =>
        Promise.resolve({
          reportKey: "rk-1",
          title: "央行宣布降准 0.25 个百分点",
          summary: "释放长期资金约 5000 亿元。",
          publishedAt: "2026-11-25T06:30:00Z",
          timeLabel: "11月25日 14:30",
          relativeTime: "2 小时前",
          sourceName: "中国人民银行",
          sourceTier: "官方原文",
          originalUrl: "https://www.pbc.gov.cn/1",
          bucket: "macro",
          bucketName: "宏观与政策",
          tags: ["货币政策"],
          eventSummary: { storyId: "st-pboc", title: "央行降准主线", reportCount: 3, milestoneCount: 2 },
          followups: [
            { reportKey: "rk-2", title: "路透社：降准配合年底流动性", sourceName: "路透社", publishedAt: null, relativeTime: "1 小时前", originalUrl: "https://reuters.com", role: "report" },
          ],
        }),
      financialNewsEvent: () => Promise.reject(new Error("unused")),
    },
    { eventId: "rk-1" },
  );
  await flush();

  const text = page.text();
  assert.match(text, /事件后续\s+·\s+1/);
  assert.match(text, /查看完整事件/);
  assert.match(text, /同事件/);
  const eventLink = page.findAll((n) => n.props?.to === "/finance/news/event/st-pboc");
  assert.equal(eventLink.length, 1);
});

test("FinancialEventDetail renders overview, milestones, whyHot, timeline and heat tabs", async () => {
  const page = await mountPage(
    "../src/pages/FinancialEventDetail.tsx",
    "FinancialEventDetail",
    {
      financialNewsTrackedEvent: () =>
        Promise.resolve({
          storyId: "st-pboc",
          title: "中国央行实施年内第二次降准",
          bucket: "macro",
          bucketName: "宏观与政策",
          statusTag: "热点事件 · 持续更新",
          reportCount: 2,
          sourceCount: 2,
          firstReportLabel: "11月12日 首发",
          latestUpdateLabel: "2 小时前更新",
          overview: { paragraphs: ["央行降准释放长期资金约 5000 亿元。"], latestMilestoneSummary: "正式公告落地" },
          milestones: [
            {
              milestoneId: "ms-1",
              title: "央行正式公告降准 0.25 个百分点",
              occurredAt: "2026-11-25T06:30:00Z",
              timeLabel: "11月25日 14:30",
              reportCount: 2,
              sourceSummary: "中国人民银行 · 路透社",
              marketNote: "10年期国债收益率小幅下行",
              representativeReportKey: "rk-1",
              reports: [
                { reportKey: "rk-1", title: "央行公告", sourceName: "中国人民银行", sourceTier: "官方原文", publishedAt: null, timeLabel: "11月25日 14:30", originalUrl: "https://www.pbc.gov.cn/" },
                { reportKey: "rk-2", title: "路透跟进", sourceName: "路透社", sourceTier: "精选报道", publishedAt: null, timeLabel: "11月25日 14:45", originalUrl: "https://reuters.com/" },
              ],
            },
          ],
          reports: [
            { reportKey: "rk-1", title: "央行公告", sourceName: "中国人民银行", sourceTier: "官方原文", publishedAt: null, timeLabel: "11月25日 14:30", originalUrl: "https://www.pbc.gov.cn/" },
          ],
          whyHot: {
            heatIndex: 19.5,
            participants48h: 8,
            newParticipants6h: 3,
            officialCount: 1,
            headline: "过去 48 小时，有 8 个独立信源报道或跟进了这件事。",
            detail: "已剔除同源重复转载。",
            badges: ["1 家官方机构", "8 个独立信源"],
          },
          heatSeries: [{ label: "11/25", value: 24, milestone: "降准落地" }],
          tags: ["货币政策"],
          recordMeta: { firstAt: "11月12日 17:10", latestAt: "11月25日 14:45", nodeCount: 1 },
        }),
    },
    { storyId: "st-pboc" },
  );
  await flush();

  const text = page.text();
  assert.match(text, /先了解这件事/);
  assert.match(text, /事件进展/);
  assert.match(text, /为什么热/);
  assert.match(text, /报道时间线\s+\(\s*1\s*\)/);

  const timelineBtn = page.findAll((n) => n.type === "button" && typeof n.props?.children === "object" && String(n.props.children).includes("报道时间线"))[0]
    || page.findAll((n) => n.type === "button" && Array.isArray(n.props?.children) && n.props.children.join("").includes("报道时间线"))[0];
  assert.ok(timelineBtn);
  timelineBtn.props.onClick();
  assert.match(page.text(), /该事件全部精选报道时间线/);

  const heatBtn = page.findAll((n) => n.type === "button" && n.props?.children === "热度趋势")[0];
  assert.ok(heatBtn);
  heatBtn.props.onClick();
  assert.match(page.text(), /事件热度与关键节点走势/);
});
