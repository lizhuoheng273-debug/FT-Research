"""Central API access classification used by public/demo deployments."""

from __future__ import annotations

import re


_PUBLIC = {("GET", "/api/health"), ("POST", "/api/auth/login"), ("POST", "/api/auth/guest")}
_AUTH = {
    ("GET", "/api/auth/me"), ("POST", "/api/auth/heartbeat"), ("POST", "/api/auth/logout"),
    ("GET", "/api/ai/status"), ("GET", "/api/ai/news"), ("GET", "/api/ai/news/hot-topics"),
    ("GET", "/api/ai/news/snapshot"), ("GET", "/api/ai/news/changes"), ("GET", "/api/ai/dailies/latest"),
    ("GET", "/api/ai/rss/sources"), ("POST", "/api/ai/rss/resolve"),
    ("POST", "/api/finance/news/calendar/refresh"), ("POST", "/api/finance/news/refresh"),
}
_OWNER_EXACT = {
    ("POST", "/api/ai/rss/refresh"), ("POST", "/api/reflect"),
    ("GET", "/api/portfolio"), ("POST", "/api/portfolio/holding"), ("DELETE", "/api/portfolio/holding"),
    ("POST", "/api/portfolio/close"), ("DELETE", "/api/portfolio/close"), ("POST", "/api/portfolio/refresh"),
    ("GET", "/api/myreports"), ("POST", "/api/myreports"),
}
_OWNER_PREFIXES = ("/api/myreports/file/", "/api/myreports/", "/api/portfolio/")

_MARKET_READ = {
    "/api/indices", "/api/quote", "/api/valuation", "/api/valuation/percentile", "/api/financials",
    "/api/announcements", "/api/reports", "/api/news", "/api/info", "/api/disclosure", "/api/kline",
    "/api/market/chart", "/api/finance", "/api/margin", "/api/block-trade", "/api/holders", "/api/dividend",
    "/api/fund-flow", "/api/dragon-tiger", "/api/lockup", "/api/blocks", "/api/hot-concepts",
    "/api/investor-qa", "/api/industry", "/api/global/indices", "/api/global/stock", "/api/global/hk/cashflow",
    "/api/radar", "/api/market/overview", "/api/market/review", "/api/market/emotion", "/api/market/turnover-top",
    "/api/finance/news/overview", "/api/finance/news/feed", "/api/finance/news/status", "/api/finance/news/calendar",
    "/api/finance/news/events/", "/api/signals/gpu-rent", "/api/ai/news/stories/", "/api/ai/reports/",
}


def _matches(path: str, candidate: str) -> bool:
    return path == candidate or (candidate.endswith("/") and path.startswith(candidate))


def policy_for(method: str, path: str) -> str:
    method, path = method.upper(), path.split("?", 1)[0]
    if (method, path) in _PUBLIC:
        return "public"
    if (method, path) in _OWNER_EXACT or any(path.startswith(prefix) for prefix in _OWNER_PREFIXES):
        return "owner"
    if (method, path) in _AUTH:
        return "authenticated"
    if method == "GET" and any(_matches(path, item) for item in _MARKET_READ):
        return "authenticated"
    if method == "GET" and re.fullmatch(r"/api/runs/[^/]+/events", path):
        return "authenticated"
    if method in {"GET", "POST", "PATCH", "DELETE"} and path.startswith("/api/conversations"):
        return "authenticated"
    if method == "POST" and path in {"/api/chat", "/api/debate"}:
        return "authenticated"
    return "deny"


def allowed_tools(principal) -> set[str]:
    from tools import TOOL_NAMES
    if getattr(principal, "kind", None) == "owner":
        return set(TOOL_NAMES)
    return {"query_quote", "query_market", "query_news_radar", "query_global_stock", "query_hk_cashflow"}
