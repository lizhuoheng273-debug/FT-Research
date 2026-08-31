"""Validated metadata for public financial-news sources.

This module deliberately validates registration metadata only.  A registered
URL is not treated as an API; fetchers remain explicit adapters in the existing
news layers and their runtime health is reported separately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "financial_news_sources.json"
_TIER_SCORES = {"S": 35, "A": 28, "B": 18, "C": 8}
_ALLOWED_TYPES = {"adapter", "rss", "html"}


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(path or DEFAULT_REGISTRY)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load source registry: {source_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("registry must be an object")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("registry.sources must be a list")
    return payload


def validate_source(source: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(source, dict):
        return ["source must be an object"]
    if not str(source.get("id") or "").strip():
        errors.append("id is required")
    if not str(source.get("name") or "").strip():
        errors.append("name is required")
    if source.get("tier") not in _TIER_SCORES:
        errors.append("tier must be one of S/A/B/C")
    if source.get("type") not in _ALLOWED_TYPES:
        errors.append("type must be adapter/rss/html")
    url = str(source.get("url") or "")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        errors.append("url must use https")
    if not parsed.netloc:
        errors.append("url must include a host")
    for field in ("owner", "timeField", "attribution"):
        if not str(source.get(field) or "").strip():
            errors.append(f"{field} is required")
    compliance = source.get("compliance")
    if not isinstance(compliance, dict) or not compliance.get("public") or not str(compliance.get("redlinePolicy") or "").strip():
        errors.append("compliance must declare public and redlinePolicy")
    return errors


def source_tier(name: str, registry: dict[str, Any] | None = None) -> int:
    payload = registry or load_registry()
    target = str(name or "").strip().lower()
    for source in payload.get("sources") or []:
        registered = str(source.get("name") or "").strip().lower()
        if target == registered or (registered and registered in target):
            return int(source.get("score") or _TIER_SCORES[source["tier"]])
    return 8


def source_grade(name: str, registry: dict[str, Any] | None = None) -> str:
    payload = registry or load_registry()
    target = str(name or "").strip().lower()
    for source in payload.get("sources") or []:
        registered = str(source.get("name") or "").strip().lower()
        if target == registered or (registered and registered in target):
            return str(source.get("tier") or "C")
    return "C"


def registry_status(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = registry or load_registry()
    tiers = {tier: 0 for tier in _TIER_SCORES}
    valid = 0
    for source in payload.get("sources") or []:
        tier = source.get("tier")
        if tier in tiers:
            tiers[tier] += 1
        if not validate_source(source):
            valid += 1
    total = len(payload.get("sources") or [])
    return {"total": total, "valid": valid, "invalid": total - valid, "tiers": {k: v for k, v in tiers.items() if v}}
