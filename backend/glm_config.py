"""Server-side GLM configuration.

The browser only receives a redacted status object.  API keys are read on each
request so local development can update ``.env`` and restart the server without
changing the frontend bundle.
"""

from __future__ import annotations

import os

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"


def load_glm_config() -> dict[str, str]:
    return {
        "provider": "glm",
        "baseURL": os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
        "apiKey": os.environ.get("GLM_API_KEY", "").strip(),
        "model": os.environ.get("GLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
    }


def public_status() -> dict[str, object]:
    cfg = load_glm_config()
    return {
        "configured": bool(cfg["apiKey"]),
        "model": cfg["model"],
        "base_url": cfg["baseURL"],
        "key_present": bool(cfg["apiKey"]),
    }
