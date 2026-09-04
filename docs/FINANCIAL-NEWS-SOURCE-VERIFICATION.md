# 金融市场资讯来源验证记录

更新时间：2026-09-02

登记表：`backend/financial_news_sources.json`。登记表示来源元数据已核对，不等于运行时采集成功；运行状态由 `/api/finance/news/status` 单独报告。

## 官方 RSS

- Federal Reserve feed 页面：<https://www.federalreserve.gov/feeds/feeds.htm>
- 采用真实 press releases feed：<https://www.federalreserve.gov/feeds/press_all.xml>
- ECB feed 页面：<https://www.ecb.europa.eu/home/html/rss.en.html>
- 采用真实 press releases feed：<https://www.ecb.europa.eu/rss/press.html>

两处官方页面均明确提供 RSS 订阅入口；本项目只登记公开 feed URL，不把公开参考汇率当作实时交易报价。

## 已登记的适配器/RSS来源

AKShare 财联社、同花顺、东方财富、新浪快讯；华尔街见闻、经济观察网、东方财富 RSS；CNBC、Financial Times、MarketWatch、Yahoo Finance、Seeking Alpha；SEC、Federal Reserve、European Central Bank；OilPrice、国际能源网、DIGITIMES、EE Times、Semiconductor Engineering，以及已有产业媒体集合。

## 运行状态语义

- `configured`：注册项通过结构校验；不代表上游已成功返回。
- `enabled`：该来源允许参与后台采集。
- `lastSuccessAt`：最近一次成功采集时间。
- `lastFailure` / `lastFailureAt`：最近一次失败原因和时间。
- `cache`：`fresh`、`stale` 或 `missing`。

未验证或失败来源不得在 UI 中宣称“已接通”；失败时保留最近成功快照并标记 stale。
