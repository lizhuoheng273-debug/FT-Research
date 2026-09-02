# AI 热点资讯媒体订阅流设计

**日期：** 2026-09-02
**目标：** 在 `/ai/news` 保留 AI HOT 热点榜，并将重复事件卡替换为可本地个性化的国内科技媒体 RSS 订阅流。

## 边界

后端新增一个 RSS 领域模块，负责内置源注册、RSS/Atom 解析、摘要清洗、受限抓取和按 URL 哈希的缓存；`/api/radar` 继续返回原赛道聚合，同时扩展同一份缓存中的逐媒体条目与健康状态。新增 `/api/ai/rss/sources` 只读缓存内置源和已验证自定义源的快照，`POST /api/ai/rss/resolve` 仅验证并预览单个 URL，不记录用户关系。前端只把排序、置顶、隐藏和自定义源 URL 存在访客浏览器本地。

前端拆出 `AIHotTopics` 和 `AISubscriptionFeed`：热点榜继续服务 `/ai/news` 与 AI 日报，媒体流只服务 `/ai/news`。媒体卡片只输出可信的文本字段，原文通过新标签打开；自定义源不能通过前端注入 HTML。搜索仅作用于当前媒体名称，拖拽支持 pointer 与键盘移动按钮，隐藏/删除/恢复均可逆。

## 数据契约

```text
RssSource = {
  id, name, category, region, priority, homepage,
  lastSuccessAt, stale, error,
  items: [{ id, title, summary, publishedAt, originalUrl }]
}
```

内置源按固定顺序：IT之家、量子位、机器之心、智东西、新智元、36氪、钛媒体、虎嗅、动点科技、Solidot、白鲸出海、月光博客。默认仅这些 `region=cn` 源可见。每个源最多保留最新三条展示条目，但缓存保存该媒体去重前的条目以免赛道聚合丢失内容。失败返回真实上次缓存并设置 `stale=true`；没有成功缓存的源返回空条目、`error` 和 `lastSuccessAt=null`。

## 安全与刷新

RSS URL 仅接受 HTTP/HTTPS、拒绝用户名密码、拒绝 localhost/回环/内网/链路本地/云元数据地址；每次重定向都重新验证目标。连接超时、读取超时、重定向次数、响应体大小和并发数均有硬上限。解析使用 XML 标准库，禁用外部实体语义，摘要只保留清洗后的文本，禁止原始 HTML 进入 JSON。内置源由后台 30 分钟调度刷新；自定义源只在 resolve 时抓取并按规范化 URL SHA-256 写入 `backend/.cache/rss/`。

## 前端状态

`localStorage` 只保存：`order`、`pinned`、`hidden`、`custom`（id/name/url）。加载服务端源后按本地配置排序，置顶优先，隐藏源不渲染。恢复默认清空个性化配置并回到十二个内置源；删除只允许自定义源。添加 RSS 成功后保存后端返回的规范化源信息，失败不产生本地关系。

## 验收

后端覆盖缓存结构、最新三条、失败降级、RSS/Atom、URL SSRF 防护和重定向复验；前端覆盖去除精选事件、搜索定位、高亮、拖拽/键盘排序、置顶/隐藏/恢复、自定义源增删、本地持久化与原文外链；日报继续渲染热点榜和事件卡片。最终运行后端离线测试、前端测试、`tsc -b` 和生产构建，且提交不包含缓存或用户数据。
