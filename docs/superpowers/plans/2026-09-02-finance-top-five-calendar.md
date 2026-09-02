# 全球财经热点与未来重要事件实施计划

> 使用 executing-plans 在当前任务逐项执行；测试先行，保留已有未提交的复盘和 RSS 修复。

**Goal:** 金融资讯首页只展示最多五条多源财经热点，以及未来十四天有官方依据的重要日程。

**Architecture:** 保留原有金融资讯合同与存储。新增独立的财经相关性/来源归属规则和官方日程缓存层；原始 RSS 报道在金融聚类前不跨媒体删除。前端两个独立加载区块共享当前金融 AI 工作台上下文。

**Tech Stack:** Python / FastAPI / requests / BeautifulSoup / SQLite，React / TypeScript / Tailwind。

**Spec:** 本任务用户已批准的两模块设计（全球财经热点榜、未来重要事件）。

## 约束

- 首页最多五条，至少两个独立编辑来源；相同通讯社转载不重复计数，不够五条不凑数。
- 只收录财经金融经济及具有直接经济影响的消息，排除普通环境、娱乐和社会消息。
- 删除灰色摘要与我的关注，保留来源/时间/缓存警告；标题外链打开原文。
- 日程只取未来十四天，北京时间展示、无具体时间不捏造、结束即移除、失败用真实缓存。
- 不购买数据，不绕过付费墙，不改行情/GLM调用合同，不自动提交推送。

## 1. 热点规则与来源链路

- [x] 测试环境/娱乐排除、金融纳入、转载计数、五条上限、时效、原始报道保留。
- [x] 新建 `backend/financial_editorial.py`，财经类别判定与原始来源归属；`financial_news.py`接入并提高差异化排序。
- [x] `newsradar.py`保存去重前报道及逐源抓取状态；`source_registry.py`区分登记和实际健康状态。
- [x] 测试新增规则并回归 financial_news / newsradar / source_registry。

## 2. 官方日程

- [x] 新建 `backend/tests/test_financial_calendar.py`，固定 Fed HTML/BLS ICS/企业活动 fixture，测试时区、十四天边界、日期精度、取消、缓存降级。
- [x] 新建 `backend/financial_calendar.py`，独立采集官方日历、规范模型、逐源原子缓存、定时更新。
- [x] `app.py`注册 `/api/finance/news/calendar`，读取缓存，不在 GET 时现场联网。
- [x] 验证真实官方入口，解析失败不覆盖已有成功缓存；不返回原始 HTML。

## 3. 两区页面与 AI 上下文

- [x] 行为测试真实 React 页面：五行标题、外链、无摘要/关注；日历日期、错误和空状态。
- [x] `FinancialNews.tsx`改为热点列表与日期轴，独立加载/取消请求，保留问 AI 入口。
- [x] `api.ts`新增日程类型；`FinanceAiWorkspace.tsx`新闻上下文换成五条热点和未来日程。
- [x] 前端完整测试、TypeScript与构建；本地浏览器验收桌面布局及外链。

## 验收

运行 `python -m pytest` 对本次相关后端测试；运行 `npm test` 与 `npm run build`。检查 git diff，重启对应本地后端，确认真实 API 与页面一致。汇报已接通来源和仍不可用来源，禁止将登记当作成功。

## 2026-09-02 验收记录

- 后端 `python -m pytest -m 'not live' -q`：357 passed，12 个联网测试排除。
- 前端全量：107 passed；TypeScript 与 Vite 生产构建通过（保留现有大包警告）。
- 额外尝试联网全量测试时，两个原有港美股测试因东方财富搜索返回非 JSON 失败；没有扩展本次范围修改证券搜索。
- 本地真实数据：中新网财经、BBC财经、Guardian Business、CNBC 均成功返回6条；还验证到 Financial Times、华尔街见闻等来源。榜单按多源规则筛选，不保证每个接入媒体都入榜。
- 官方日程：Fed / ECB / BEA / NVIDIA 四源可用，未来十四天当前10条；BLS返回403，页面明确提示覆盖不完整，不绕过限制。
- 独立审查修正：来源元数据经 SQLite 不丢失；FOMC会议纪要不误标利率决议；日期型事件按源时区过期；残缺ICS不覆盖缓存。
- 实测修正：盘前多事件汇总不能连接互不相干事件；移除已退役A股反查网络依赖；RSS批次60秒截止，保留已完成信源。
- 页面为标题榜 + 官方日程双区；外链新标签、无横向溢出、统一AI上下文已实测。未新增付费数据源，未提交或推送。
