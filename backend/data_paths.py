"""Persistent runtime paths shared by local and container deployments."""

from __future__ import annotations

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent


def data_root() -> Path | None:
    value = os.environ.get("VR_DATA_DIR", "").strip()
    return Path(value).expanduser() if value else None


def persistent_path(*parts: str, legacy: str | Path) -> Path:
    root = data_root()
    return root.joinpath(*parts) if root else Path(legacy)


def cache_path(name: str, *, legacy: str | Path | None = None) -> Path:
    return persistent_path("cache", name, legacy=legacy or BACKEND_DIR / ".cache" / name)
