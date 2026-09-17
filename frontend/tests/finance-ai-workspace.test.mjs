import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";
import vm from "node:vm";

const root = new URL("../src/", import.meta.url);
const router = await readFile(new URL("router.tsx", root), "utf8");
const askAi = await readFile(new URL("components/ui/AskAiButton.tsx", root), "utf8");
const financeAi = await readFile(new URL("lib/financeAi.ts", root), "utf8");
const daily = await readFile(new URL("pages/DailyReview.tsx", root), "utf8");
const financial = await readFile(new URL("pages/FinancialNews.tsx", root), "utf8");
const financialDetail = await readFile(new URL("pages/FinancialNewsDetail.tsx", root), "utf8");
const index = await readFile(new URL("pages/IndexDetail.tsx", root), "utf8");
const sector = await readFile(new URL("pages/SectorDetail.tsx", root), "utf8");
const watchlist = await readFile(new URL("pages/Watchlist.tsx", root), "utf8");
const stockData = await readFile(new URL("pages/StockData.tsx", root), "utf8");
const stockDetail = await readFile(new URL("pages/StockDetail.tsx", root), "utf8");
const aiWorkspace = await readFile(new URL("pages/AiConversationWorkspace.tsx", root), "utf8");

async function loadFinanceAiApi() {
  const compiled = ts.transpileModule(financeAi, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, URLSearchParams });
  return module.exports;
}

function mountAiWorkspace({ query = "source=ai-news", from = "/ai/news", locationState, responses = {} } = {}) {
  const slots = [];
  const effects = [];
  const requests = [];
  const navigations = [];
  let cursor = 0;
  let mounted = false;
  let sessionOptions;
  const react = {
    useRef(initial) {
      const index = cursor++;
      return slots[index] ??= { current: initial };
    },
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], (value) => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useEffect(effect) {
      cursor++;
      if (!mounted) effects.push(effect);
    },
  };
  const exports = {};
  const compiled = ts.transpileModule(aiWorkspace, { compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const response = (body, ok = true, status = 200) => ({ ok, status, json: async () => body });
  const fetcher = async (url) => {
    requests.push(url);
    const path = String(url).replace(/^\/api/, "");
    const result = responses[path];
    if (!result) throw new Error(`unexpected request: ${path}`);
    return typeof result === "function" ? result() : response(result.body, result.ok, result.status);
  };
  const require = (name) => {
    if (name === "react") return react;
    if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    if (name === "react-router-dom") return {
      useSearchParams: () => [new URLSearchParams(query)],
      useLocation: () => ({ state: locationState ?? { from }, search: "" }),
      useNavigate: () => (to, options) => navigations.push({ to, options }),
    };
    if (name === "@/hooks/useAiChatSession") return { useAiChatSession: (options) => {
      sessionOptions = options;
      return { messages: [], conversationId: undefined, clearChat() {} };
    } };
    if (name === "@/lib/api") return { apiUrl: (path) => `/api${path}`, authHeaders: () => ({}) };
    if (name === "@/lib/utils") return { cn: (...classes) => classes.filter(Boolean).join(" ") };
    return new Proxy({}, { get: (_target, key) => key });
  };
  new Function("require", "exports", "fetch", compiled)(require, exports, fetcher);

  function render() {
    cursor = 0;
    const tree = exports.AiConversationWorkspace();
    if (!mounted) {
      mounted = true;
      effects.forEach((effect) => effect());
    }
    return tree;
  }
  const tree = render();
  return {
    render,
    requests,
    navigations,
    get sessionOptions() { return sessionOptions; },
  };
}

function mountAskAiButton({ pathname = "/ai/news/story/story-1", search = "", state = null } = {}) {
  const navigations = [];
  const exports = {};
  const compiled = ts.transpileModule(askAi, { compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const require = (name) => {
    if (name === "react") return { useState: (initial) => [initial, () => {}], useEffect: () => {} };
    if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: "fragment" };
    if (name === "react-router-dom") return {
      Link: "Link",
      useLocation: () => ({ pathname, search, state }),
      useNavigate: () => (to, options) => navigations.push({ to, options }),
    };
    if (name === "@/hooks/useAiChatSession") return { useAiChatSession: () => ({ messages: [] }) };
    if (name === "@/lib/financeAi") return {
      buildAiWorkspacePath: (_source, identifiers) => `/ai/conversations?source=ai-news&eventId=${identifiers.eventId}`,
    };
    if (name === "@/lib/llm") return { hasLlm: () => false };
    return new Proxy({}, { get: (_target, key) => key });
  };
  new Function("require", "exports", "window", compiled)(require, exports, { location: { search } });
  return { render: (props) => exports.AskAiButton(props), navigations };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

function findButton(node, label) {
  if (Array.isArray(node)) return node.map((child) => findButton(child, label)).find(Boolean);
  if (!node || typeof node !== "object") return undefined;
  const text = (value) => Array.isArray(value) ? value.map(text).join(" ") :
    value && typeof value === "object" ? text(value.props?.children) : String(value ?? "");
  if (node.type === "button" && text(node.props?.children).includes(label)) return node.props;
  return findButton(node.props?.children, label);
}

function findHeading(node) {
  if (Array.isArray(node)) return node.map(findHeading).find(Boolean);
  if (!node || typeof node !== "object") return undefined;
  if (node.type === "h1") return node.props?.children;
  return findHeading(node.props?.children);
}

function nodeText(node) {
  if (node == null || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map(nodeText).join(" ");
  if (typeof node !== "object") return String(node);
  return nodeText(node.props?.children);
}

test("finance AI workspace exposes the shared route and all source keys", async () => {
  const workspaceUrl = new URL("pages/FinanceAiWorkspace.tsx", root);
  const workspace = await readFile(workspaceUrl, "utf8");
  assert.match(router, /path:\s*["']\/finance\/ai["']/);
  assert.match(router, /FinanceAiWorkspace/);
  assert.match(router, /\/finance\/stocks\/:code\/ai[\s\S]*FinanceAiWorkspace/);
  for (const source of ["review", "news", "watchlist", "index", "stock", "stock-panel", "news-story"]) assert.match(workspace, new RegExp(`"${source}"`));
  for (const key of ["review:", "news", "news-story:", "watchlist", "index:", "stock:", "stock-panel:"]) assert.match(financeAi, new RegExp(key.replace(/[<>]/g, "\\$&")));
  assert.match(workspace, /useSearchParams/);
  assert.match(workspace, /useAiChatSession/);
  assert.match(workspace, /AiConversation/);
  assert.match(workspace, /ConversationRail/);
  assert.doesNotMatch(workspace, /已带入上下文/);
  assert.doesNotMatch(workspace, /工具调用记录/);
  assert.match(workspace, /state\.from|location\.state/);
  assert.doesNotMatch(workspace, /JSON\.stringify\([^)]*\)\.replace/);
});

test("workspace route target supports source identifiers without putting context in the URL", () => {
  assert.match(askAi, /workspaceSource/);
  assert.match(askAi, /navigate\(/);
  for (const page of [daily, financial, financialDetail, index, sector, watchlist, stockData]) {
    assert.match(page, /workspaceSource=/);
  }
  assert.match(stockDetail, /\/finance\/ai\?source=stock&code=/);
  assert.doesNotMatch(stockDetail, /to=\{`\/finance\/stocks\/\$\{code\}\/ai`\}/);
});

test("AI news workspace route serializes its selected event ID and encodes it as a query value", async () => {
  const api = await loadFinanceAiApi();
  assert.equal(api.buildAiWorkspacePath("ai-news", { eventId: "story-1" }), "/ai/conversations?source=ai-news&eventId=story-1");
  assert.equal(api.buildAiWorkspacePath("ai-news", { eventId: "story 1&next" }), "/ai/conversations?source=ai-news&eventId=story+1%26next");
  assert.equal(api.buildAiWorkspacePath("ai-daily", { date: "2026-09-17" }), "/ai/conversations?source=ai-daily&date=2026-09-17");
});

test("Ask AI hands off a serializable story snapshot and preserves detail return state", () => {
  const fallback = { title: "路由备用标题", summary: "路由备用摘要", links: { original: "https://example.com/fallback" } };
  const snapshot = { title: "即时标题", summary: "即时摘要", latest: "即时进展", originalUrl: "https://example.com/original" };
  const app = mountAskAiButton({ search: "?tab=latest", state: { fallback } });
  const button = app.render({
    context: "unused",
    workspaceSource: "ai-news",
    workspaceEventId: "story-1",
    workspaceSnapshot: snapshot,
    workspaceReturnState: { fallback },
  });
  button.props.onClick();

  assert.equal(app.navigations[0].to, "/ai/conversations?source=ai-news&eventId=story-1");
  assert.deepEqual(app.navigations[0].options.state, {
    from: "/ai/news/story/story-1?tab=latest",
    returnState: { fallback },
    storySnapshot: snapshot,
  });
  assert.doesNotThrow(() => JSON.stringify(app.navigations[0].options.state));
});

test("AI-news workspace names the selected story immediately and upgrades the header after fetch", async () => {
  let resolveStory;
  const pending = new Promise((resolve) => { resolveStory = resolve; });
  const app = mountAiWorkspace({
    query: "source=ai-news&eventId=story-1",
    locationState: {
      from: "/ai/news/story/story-1",
      storySnapshot: { title: "即时备用标题", summary: "即时摘要", originalUrl: "https://example.com/immediate" },
    },
    responses: { "/ai/news/stories/story-1": () => pending },
  });

  assert.equal(findHeading(app.render()), "即时备用标题");
  assert.match(app.sessionOptions.context, /即时摘要/);
  assert.match(app.sessionOptions.context, /https:\/\/example\.com\/immediate/);
  resolveStory({ ok: true, status: 200, json: async () => ({ story: { title: "接口完整标题", digest: "接口完整摘要" } }) });
  await flush();
  await flush();
  assert.equal(findHeading(app.render()), "接口完整标题");
  assert.match(app.sessionOptions.context, /接口完整摘要/);
});

test("AI-news conversation loads selected story context, identity, metadata and returns to its detail route", async () => {
  const story = {
    title: "芯片公司发布新模型",
    digest: "摘要内容",
    latest: "最新进展内容",
    links: { original: "https://example.com/story" },
    reports: [{
      title: "媒体报道标题",
      summary: "媒体报道摘要",
      source: { name: "示例媒体" },
      publishedAt: "2026-09-17",
      links: { original: "https://example.com/report" },
    }],
  };
  const from = "/ai/news/story/story-1?tab=latest";
  const app = mountAiWorkspace({
    query: "source=ai-news&eventId=story-1",
    from,
    responses: { "/ai/news/stories/story-1": { body: { story } } },
  });
  await flush();
  await flush();
  app.render();

  assert.deepEqual(app.requests, ["/api/ai/news/stories/story-1"]);
  assert.equal(app.sessionOptions.conversationKey, "ai:ai-news:story-1");
  assert.equal(app.sessionOptions.source.type, "ai-news");
  assert.equal(app.sessionOptions.source.eventId, "story-1");
  assert.equal(app.sessionOptions.source.date, "");
  for (const value of [story.title, story.digest, story.latest, "媒体报道标题", "媒体报道摘要", "示例媒体", "https://example.com/story", "https://example.com/report"]) {
    assert.ok(app.sessionOptions.context.includes(value), `context should include ${value}`);
  }

  findButton(app.render(), "返回").onClick();
  assert.equal(app.navigations.length, 1);
  assert.equal(app.navigations[0].to, from);
  assert.equal(app.navigations[0].options.replace, true);
});

test("AI news without an event retains general context and AI Daily keeps its date identity", async () => {
  const general = mountAiWorkspace({
    query: "source=ai-news",
    responses: {
      "/ai/news/hot-topics": { body: { items: [{ rank: 1, title: "当前热点", source: "示例源" }] } },
      "/ai/news?mode=selected&window=24h&limit=50": { body: { items: [{ title: "订阅资讯", source: "订阅源" }] } },
    },
  });
  await flush();
  await flush();
  general.render();
  assert.deepEqual(general.requests.sort(), ["/api/ai/news/hot-topics", "/api/ai/news?mode=selected&window=24h&limit=50"].sort());
  assert.equal(general.sessionOptions.conversationKey, "ai:ai-news:latest");
  assert.match(general.sessionOptions.context, /当前热点/);
  assert.match(general.sessionOptions.context, /订阅资讯/);

  const daily = mountAiWorkspace({ query: "source=ai-daily&date=2026-09-17" });
  await flush();
  daily.render();
  assert.deepEqual(daily.requests, []);
  assert.equal(daily.sessionOptions.conversationKey, "ai:ai-daily:2026-09-17");
  assert.match(daily.sessionOptions.context, /2026-09-17/);
});

test("AI-news story IDs are encoded in the detail request", async () => {
  const encoded = mountAiWorkspace({
    query: "source=ai-news&eventId=story%2Fone",
    responses: { "/ai/news/stories/story%2Fone": { body: { title: "编码故事" } } },
  });
  await flush();
  await flush();
  encoded.render();
  assert.deepEqual(encoded.requests, ["/api/ai/news/stories/story%2Fone"]);
  assert.equal(encoded.sessionOptions.conversationKey, "ai:ai-news:story/one");
  assert.equal(encoded.sessionOptions.source.eventId, "story/one");
});

test("failed story fetch keeps its warning but enables meaningful fallback context", async () => {
  const fallback = { title: "失败备用标题", summary: "失败备用摘要", originalUrl: "https://example.com/fallback" };
  const returnState = { fallback: { title: "详情标题", summary: "详情摘要" } };
  const missing = mountAiWorkspace({
    query: "source=ai-news&eventId=missing-story",
    locationState: { from: "/ai/news/story/missing-story", returnState, storySnapshot: fallback },
    responses: { "/ai/news/stories/missing-story": { body: { detail: "Not Found" }, ok: false, status: 404 } },
  });
  assert.equal(missing.sessionOptions.contextReady, true);
  await flush();
  await flush();
  missing.render();
  assert.deepEqual(missing.requests, ["/api/ai/news/stories/missing-story"]);
  assert.match(missing.sessionOptions.context, /失败备用标题/);
  assert.match(missing.sessionOptions.context, /失败备用摘要/);
  assert.match(missing.sessionOptions.context, /https:\/\/example\.com\/fallback/);
  assert.equal(missing.sessionOptions.contextReady, true);
  assert.match(nodeText(missing.render()), /上下文异常/);
  assert.equal(findHeading(missing.render()), "失败备用标题");
  assert.equal(missing.sessionOptions.conversationKey, "ai:ai-news:missing-story");

  findButton(missing.render(), "返回").onClick();
  assert.equal(missing.navigations[0].to, "/ai/news/story/missing-story");
  assert.equal(missing.navigations[0].options.replace, true);
  assert.deepEqual(missing.navigations[0].options.state, returnState);
});

test("failed story fetch blocks sending when route state has no meaningful context", async () => {
  for (const [eventId, storySnapshot] of [
    ["title-only", { title: "只有标题" }],
    ["no-snapshot", undefined],
  ]) {
    const app = mountAiWorkspace({
      query: `source=ai-news&eventId=${eventId}`,
      locationState: { from: `/ai/news/story/${eventId}`, storySnapshot },
      responses: { [`/ai/news/stories/${eventId}`]: { body: { detail: "Not Found" }, ok: false, status: 404 } },
    });
    await flush();
    await flush();
    app.render();

    assert.equal(app.sessionOptions.contextReady, false);
    assert.equal(app.sessionOptions.conversationKey, `ai:ai-news:${eventId}`);
    assert.match(nodeText(app.render()), /上下文异常/);
  }
});

test("index detail copy reflects all six supported review indices", () => {
  assert.match(index, /支持六个主要 A 股指数/);
  assert.doesNotMatch(index, /支持四个主要 A 股指数/);
});
