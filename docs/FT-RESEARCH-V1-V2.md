# FT-Research V1/V2 实施说明

## 当前范围

V1 已完成金融板块产品化、FT-Research 品牌切换，以及后端托管的 GLM 5.3 Flash 文本链路。V2 已加入 AI HOT v1 的只读代理、ETag 缓存、失败回退和 AI 资讯页面基础实现。

左侧导航固定为两级：

- AI 板块：AI 热点资讯、AI 日报
- 金融板块：金融市场资讯、每日复盘、自选股、AI 投研

原有持仓、板块中心、研报、研究记录、多空辩论仍保留旧路由以兼容书签，但不再出现在产品导航中。

## 数据与 AI 边界

金融行情、K 线、财务、公告、资金面继续使用 Vibe Research 自带免费公开源，前端展示原始更新时间和失败状态；AI 只负责对页面上下文进行解释，不替代客观数据层。

GLM 配置只允许放在 `backend/.env`：

```text
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM_MODEL=glm-5.3-flash
GLM_API_KEY=...
```

浏览器调用 `/api/chat` 时只提交 `messages` 与 `context`。`/api/ai/status` 只返回模型、Base URL 和是否已配置，永不返回 Key。

AI HOT 只作为 AI 资讯源。`backend/aihot_api.py` 统一转换 `id/title/summary/score/reason/publishedAt/source/links`，并在每个 URL 上保存 ETag 与最近一次成功响应。上游 304 直接复用缓存，上游错误则返回缓存并标记 `stale=true`。获得书面授权前不要把 AI HOT 数据公开部署为聚合站。

## 本地启动

```powershell
Copy-Item backend/.env.example backend/.env
# 编辑 backend/.env 填入 GLM_API_KEY
python -m uvicorn app:app --app-dir backend --port 8900
cd frontend
npm run dev
```

## 主要 API

- `GET /api/ai/status`：GLM 配置状态
- `POST /api/chat`：GLM NDJSON 流式问答
- `GET /api/ai/news`：AI HOT 精选资讯（支持 mode/window/limit）
- `GET /api/ai/news/hot-topics`：热点榜
- `GET /api/ai/news/stories/{public_id}`：事件详情
- `GET /api/ai/dailies/latest`：最新日报

## AI 日报 / 周报 / 月报

`/ai/daily` 是周期报告中心。日报由 FT-Research 每天北京时间 08:00 将前一自然日的 AI 热点榜和精选事件固化到 `backend/.cache/ft-reports/daily/`，页面复用热点榜、事件卡片和 `/ai/news/story/:storyId` 详情页。周报和月报目前没有 AI HOT 的正式 API，后端仅在本地或私有环境抓取其网页、解析为结构化主题和媒体报道并缓存；上游不可用时继续展示最近缓存并标注 `stale`。

报告接口：

- `GET /api/ai/reports/index?kind=daily|weekly|monthly`
- `GET /api/ai/reports/daily/latest`、`/daily/{date}`
- `GET /api/ai/reports/weekly/latest`、`/weekly/{period}`
- `GET /api/ai/reports/monthly/latest`、`/monthly/{period}`

## 测试边界

后端默认测试应排除需要外网或额外数据包的 `live` 标记；GLM 与 AI HOT 测试使用模拟响应，覆盖状态脱敏、普通流式链路、字段映射、ETag 304 和缓存回退。
