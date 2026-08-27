import os

from fastapi.testclient import TestClient

import app
import glm_config


def test_glm_status_never_returns_key(monkeypatch):
    monkeypatch.setenv("GLM_API_KEY", "secret-value")
    monkeypatch.setenv("GLM_MODEL", "glm-5.3-flash")
    client = TestClient(app.app)
    body = client.get("/api/ai/status").json()
    assert body == {
        "configured": True,
        "model": "glm-5.3-flash",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_present": True,
    }
    assert "secret" not in str(body)


def test_chat_uses_server_glm_config(monkeypatch):
    monkeypatch.setenv("GLM_API_KEY", "server-key")
    monkeypatch.setenv("GLM_MODEL", "glm-test")
    seen = {}

    def fake_stream(cfg, messages, context):
        seen.update(cfg)
        yield {"type": "delta", "text": "ok"}
        yield {"type": "done", "trace": [], "rounds": 1}

    monkeypatch.setattr(app.chat_layer, "run_chat_stream", fake_stream)
    response = TestClient(app.app).post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "context": "ctx"})
    assert response.status_code == 200
    assert seen["apiKey"] == "server-key"
    assert seen["model"] == "glm-test"


def test_glm_config_defaults(monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    cfg = glm_config.load_glm_config()
    assert cfg["baseURL"] == "https://open.bigmodel.cn/api/paas/v4"
    assert cfg["model"] == "glm-5.3-flash"
    assert cfg["apiKey"] == ""
