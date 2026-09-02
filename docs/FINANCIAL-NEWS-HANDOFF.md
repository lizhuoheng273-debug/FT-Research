# 金融市场资讯交接

## 本轮范围

当前 `/finance/news` 只有两个主体区：`全球要闻速览` 与 `我的关注`。旧金融资讯路由、事件详情 API、`/api/radar`、RSS 订阅和旧 overview 字段继续兼容，但不再作为本页主体展示。

## 关键接口

- `GET /api/finance/news/overview`：新增 `globalHighlights`；旧字段含义保留。
- `POST /api/finance/news/following`：请求 `{ codes, page, pageSize }`，只查询、不持久化组合，返回去重关注流与分页信息。
- `GET /api/finance/news/status`：返回逐源静态登记和运行状态。

## 安全与降级

外链只接受 HTTP/HTTPS；缺链接显示“原文链接暂缺”。单源失败不清空成功缓存；GLM 不可用、超预算或数字校验失败时保留原始标题/摘要。页面刷新仅读缓存；关注流请求按选择版本取消或忽略旧响应。

## 当前验证证据

- 后端离线：290 passed，12 live deselected。
- 前端：95 passed。
- 生产构建：`npm run build` 通过。
- 浏览器自动化未提供，未声称完成真实桌面/移动浏览器验收；后续若接入浏览器工具，应补测展开 20 条、键盘焦点、新标签原文、空自选、缓存提示和选择切换。

## 工作区状态

本轮改动尚未推送、合并或公开部署。提交哈希以交付时 Git 输出为准。
