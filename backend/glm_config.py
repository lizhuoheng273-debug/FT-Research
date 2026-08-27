"""Server-side GLM configuration.

The browser only receives a redacted status object.  API keys are read on each
request so local development can update ``.env`` and restart the server without
changing the frontend bundle.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"
ENV_FILE = Path(__file__).with_name(".env")


def _read_env_file() -> dict[str, str]:
    """Read the small local .env file without mutating process environment."""
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key, value = key.strip(), value.strip()
        if key and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _setting(name: str, default: str, file_values: dict[str, str]) -> str:
    return os.environ.get(name, file_values.get(name, default)).strip()


def load_glm_config() -> dict[str, str]:
    file_values = _read_env_file()
    return {
        "provider": "glm",
        "baseURL": _setting("GLM_BASE_URL", DEFAULT_BASE_URL, file_values).rstrip("/"),
        "apiKey": _setting("GLM_API_KEY", "", file_values),
        "model": _setting("GLM_MODEL", DEFAULT_MODEL, file_values) or DEFAULT_MODEL,
    }


def public_status() -> dict[str, object]:
    cfg = load_glm_config()
    return {
        "configured": bool(cfg["apiKey"]),
        "model": cfg["model"],
        "base_url": cfg["baseURL"],
        "key_present": bool(cfg["apiKey"]),
    }
