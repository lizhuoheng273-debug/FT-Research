"""Pure helpers for the browser-owned stock following stream.

The module intentionally has no network or persistence responsibilities.  The
service supplies cached company profiles, direct news rows, and the shared
rolling event library; this layer only normalizes, relates, and paginates the
result.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


_CODE_RE = re.compile(r"^[0368]\d{5}$")
IMPORTANCE_THRESHOLD = 50


def normalize_codes(codes: Any) -> list[str]:
    values = [codes] if isinstance(codes, str) else (codes or [])
    result: list[str] = []
    for value in values:
        code = str(value or "").strip()
        if _CODE_RE.fullmatch(code) and code not in result:
            result.append(code)
    return result


def _text(*values: Any) -> str:
    return " ".join(str(value or "").strip() for value in values if str(value or "").strip())


def _safe_url(value: Any) -> str:
    value = str(value or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text[:10]


def _profile_boards(profile: dict[str, Any]) -> list[str]:
    boards = profile.get("boards") or profile.get("concepts") or profile.get("conceptTags") or []
    if isinstance(boards, str):
        return [boards]
    return [str(row.get("name") if isinstance(row, dict) else row).strip() for row in boards if str(row.get("name") if isinstance(row, dict) else row).strip()]


def _direct_row(code: str, name: str, raw: dict[str, Any], default_kind: str) -> dict[str, Any] | None:
    title = _text(raw.get("title"), raw.get("新闻标题"), raw.get("摘要"), raw.get("内容"))
    if not title:
        return None
    url = _safe_url(raw.get("url") or raw.get("新闻链接") or raw.get("originalUrl"))
    when = _date(raw.get("publishedAt") or raw.get("发布时间") or raw.get("date") or raw.get("公告日期"))
    kind = str(raw.get("kind") or default_kind)
    return {
        "id": str(raw.get("id") or url or f"{code}:{title}:{when}"),
        "code": code,
        "name": name or code,
        "title": title,
        "summary": _text(raw.get("summary"), raw.get("内容"), raw.get("摘要")),
        "publishedAt": when or None,
        "originalUrl": url,
        "kind": kind,
        "relationType": "个股",
        "evidence": f"{name or code} 的{kind}原始记录",
        "relatedCodes": [code],
    }


def _event_relation(event: dict[str, Any], code: str, profile: dict[str, Any]) -> tuple[str, str] | None:
    related = {str(value) for value in event.get("relatedStocks") or []}
    if code in related:
        return "个股", f"事件明确关联股票 {code}"

    blob = _text(event.get("title"), event.get("summary"), event.get("track"), event.get("category"))
    industry = str(profile.get("industry") or "").strip()
    importance = int(event.get("importanceScore") or event.get("globalScore") or 0)
    if industry and industry in blob and importance >= IMPORTANCE_THRESHOLD:
        return "行业", f"公司资料行业“{industry}”与事件主题匹配，重要性 {importance}/100"

    boards = _profile_boards(profile)
    business = str(profile.get("mainBusiness") or profile.get("businessScope") or "").strip()
    related_concepts = {str(value) for value in event.get("relatedConcepts") or event.get("concepts") or []}
    board_hit = next((board for board in boards if board in blob or board in related_concepts), "")
    # A concept is strong only if the company profile proves both membership
    # and a business-word overlap (or the event carries explicit public proof).
    business_words = {word for word in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", business.lower())}
    board_words = {word for word in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", board_hit.lower())}
    explicit = event.get("conceptEvidence")
    if board_hit and importance >= IMPORTANCE_THRESHOLD and (business_words & board_words or explicit):
        return "强关联概念", f"板块“{board_hit}”有公开归属，且主营业务/公开资料支持关联"
    return None


def build_following_stream(
    codes: Any,
    *,
    profiles: dict[str, dict[str, Any]],
    direct_rows: dict[str, list[dict[str, Any]]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = normalize_codes(codes)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for code in normalized:
        profile = profiles.get(code) or {}
        name = str(profile.get("shortName") or code)
        for raw in direct_rows.get(code) or []:
            item = _direct_row(code, name, raw, "资讯")
            if item is None:
                continue
            key = ("url", item["originalUrl"]) if item["originalUrl"] else ("text", item["title"], item["publishedAt"] or "")
            if key in seen:
                continue
            seen.add(key)
            rows.append(item)

    event_rows: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = str(event.get("id") or event.get("title") or "")
        if not event_id:
            continue
        matched: list[tuple[str, str, str]] = []
        for code in normalized:
            relation = _event_relation(event, code, profiles.get(code) or {})
            if relation:
                matched.append((code, relation[0], relation[1]))
        if not matched:
            continue
        primary_code, relation_type, evidence = matched[0]
        row = event_rows.get(event_id)
        if row is None:
            row = {
                "id": event_id,
                "code": primary_code,
                "name": str((profiles.get(primary_code) or {}).get("shortName") or primary_code),
                "title": str(event.get("title") or "未命名事件"),
                "summary": str(event.get("aiDigest") or event.get("summary") or ""),
                "publishedAt": event.get("latestAt") or event.get("publishedAt"),
                "originalUrl": _safe_url(event.get("originalUrl")),
                "kind": "事件",
                "relationType": relation_type,
                "evidence": evidence,
                "relatedCodes": [],
                "relatedSources": list(event.get("relatedSources") or []),
            }
            event_rows[event_id] = row
        row["relatedCodes"] = sorted(set(row["relatedCodes"]) | {code for code, _, _ in matched})
        if row["relationType"] != "个股" and any(kind == "个股" for _, kind, _ in matched):
            row["relationType"] = "个股"
        rows.append(row) if row not in rows else None

    return sorted(rows, key=lambda row: str(row.get("publishedAt") or ""), reverse=True)
