"""AI HOT v1 adapter with ETag validation and last-good cache fallback."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "https://aihot.virxact.com"


def normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    links = raw.get("links") or {}
    source = raw.get("source") or {}
    return {
        "id": str(raw.get("id") or hashlib.sha1(str(raw).encode()).hexdigest()[:16]),
        "title": raw.get("title") or raw.get("originalTitle") or "未命名事件",
        "summary": raw.get("summary") or "",
        "score": raw.get("score"),
        "reason": raw.get("reason") or "",
        "category": raw.get("category") or "",
        "publishedAt": raw.get("publishedAt") or raw.get("discoveredAt"),
        "source": source.get("name") if isinstance(source, dict) else str(source),
        "links": {
            "aihot": links.get("aihot"),
            "original": links.get("original"),
            "story": links.get("story"),
        },
    }


class AihotClient:
    def __init__(self, base_url: str | None = None, timeout: float = 20, cache_dir: str | None = None):
        self.base_url = (base_url or os.environ.get("AIHOT_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._cache: dict[str, tuple[str | None, dict[str, Any]]] = {}
        self._cache_dir = Path(cache_dir or os.environ.get("AIHOT_CACHE_DIR", Path(__file__).parent / ".cache" / "aihot"))

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def _load_disk(self, key: str) -> tuple[str | None, dict[str, Any]] | None:
        try:
            raw = json.loads(self._cache_path(key).read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("payload"), dict):
                return raw.get("etag"), raw["payload"]
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _save_disk(self, key: str, etag: str | None, payload: dict[str, Any]) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(key).write_text(json.dumps({"etag": etag, "payload": payload}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # Cache is an optimization; a read-only deployment still works.
            pass

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params or {}))
        etag, cached = self._cache.get(key, (None, None))
        if cached is None:
            disk = self._load_disk(key)
            if disk:
                etag, cached = disk
                self._cache[key] = disk
        headers = {"Accept": "application/json"}
        if etag:
            headers["If-None-Match"] = etag
        try:
            response = self._session.get(self.base_url + path, params=params, headers=headers, timeout=self.timeout)
            if response.status_code == 304 and cached is not None:
                return {**cached, "stale": False, "notModified": True}
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                self._cache[key] = (response.headers.get("ETag"), payload)
                self._save_disk(key, response.headers.get("ETag"), payload)
                return {**payload, "stale": False}
            raise RuntimeError("AI HOT 返回格式不是 JSON 对象")
        except Exception:
            if cached is not None:
                return {**cached, "stale": True}
            raise

    def items(self, **params: Any) -> dict[str, Any]:
        payload = self._get("/api/v1/items", params or {"mode": "selected", "window": "24h", "limit": 50})
        payload["items"] = [normalize_item(x) for x in payload.get("items", [])]
        return payload

    def hot_topics(self, **params: Any) -> dict[str, Any]:
        payload = self._get("/api/v1/hot-topics", params)
        payload["items"] = [
            {
                **item,
                "source": (item.get("source") or {}).get("name") if isinstance(item.get("source"), dict) else item.get("source"),
            }
            for item in payload.get("items", [])
        ]
        return payload

    def story(self, public_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/stories/{public_id}")

    def daily(self, date: str | None = None) -> dict[str, Any]:
        return self._get("/api/v1/dailies/latest" if not date else f"/api/v1/dailies/{date}")

    def selected_snapshot(self) -> dict[str, Any]:
        return self._get("/api/v1/selected/snapshot")

    def selected_changes(self) -> dict[str, Any]:
        return self._get("/api/v1/selected/changes")
