import json
import asyncio
import pytest
from threading import Event
from fastapi.testclient import TestClient
import app
import debate


def test_debate_uses_backend_glm_without_browser_credentials(monkeypatch):
    cfg={"provider":"glm","apiKey":"server-test-key","baseURL":"https://example.test/v4","model":"server-model"}
    monkeypatch.setattr(app.glm_config,"load_glm_config",lambda:cfg)
    seen=[]
    def stream(config,code,rounds,**kwargs):
        seen.append((config,code,rounds))
        yield {"type":"delta","stage":"bull","text":"一"}
        yield {"type":"done","stages":[]}
    monkeypatch.setattr(debate,"run_debate_stream",stream)
    with TestClient(app.app) as client:
        response=client.post('/api/debate',json={"code":"600519","rounds":1})
    assert response.status_code==200
    assert seen==[(cfg,"600519",1)]
    assert "server-test-key" not in response.text
    assert [json.loads(line)["type"] for line in response.text.splitlines()]==["delta","done"]


def test_missing_backend_key_prevents_dossier_or_model_call(monkeypatch):
    monkeypatch.setattr(app.glm_config,"load_glm_config",lambda:{"apiKey":""})
    monkeypatch.setattr(debate,"run_debate_stream",lambda *a,**k:(_ for _ in ()).throw(AssertionError("must not run")))
    response=TestClient(app.app).post('/api/debate',json={"code":"600519"})
    assert response.status_code==400
    assert "GLM" in response.json()["detail"]


def test_cancel_closes_active_model_response_and_skips_next_role(monkeypatch):
    monkeypatch.setattr(debate.tools, "exec_tool", lambda *a: {"price": 100})
    responses=[]
    class Response:
        closed=False
        def close(self): self.closed=True
    def call(*a, **k):
        response=Response(); responses.append(response); return response
    monkeypatch.setattr(debate.chat, "_call_llm_stream", call)
    monkeypatch.setattr(debate, "_iter_debate_deltas", lambda resp: iter([{"content":"第一段"},{"content":"第二段"}]))
    control=debate.DebateControl()
    stream=debate.run_debate_stream({}, "600519", control=control)
    for event in stream:
        if event["type"]=="delta": break
    control.cancel()
    assert responses[0].closed
    assert list(stream)==[]
    assert len(responses)==1


def test_cancel_during_dossier_never_calls_model(monkeypatch):
    control=debate.DebateControl()
    monkeypatch.setattr(debate.tools,"exec_tool",lambda *a:{"price":100})
    monkeypatch.setattr(debate.chat,"_call_llm_stream",lambda *a,**k:(_ for _ in ()).throw(AssertionError("cancelled")))
    stream=debate.run_debate_stream({},"600519",control=control)
    assert next(stream)["type"]=="status"
    control.cancel()
    assert list(stream)==[]


def test_response_disconnect_propagates_to_debate_control(monkeypatch):
    monkeypatch.setattr(app.glm_config,"load_glm_config",lambda:{"apiKey":"test"})
    controls=[]
    def fake(config,code,rounds,control):
        controls.append(control)
        yield {"type":"status","message":"collecting"}
        yield {"type":"done"}
    monkeypatch.setattr(debate,"run_debate_stream",fake)
    async def exercise():
        response=app.debate(app.DebateReq(code="600519"))
        await anext(response.body_iterator)
        await response.body_iterator.aclose()
    asyncio.run(exercise())
    assert controls[0].stopped.is_set()


@pytest.mark.parametrize("tail", [
    'data: {"error":{"message":"upstream failed"}}\n\ndata: [DONE]\n',
    '',
    'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\ndata: [DONE]\n',
])
def test_partial_upstream_is_never_a_successful_stage(monkeypatch, tail):
    class Response:
        def iter_content(self, chunk_size=None):
            yield ('data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'+tail).encode()
        def iter_lines(self):
            return iter(('data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'+tail).encode().splitlines())
        def close(self): pass
    monkeypatch.setattr(debate.tools,"exec_tool",lambda *a:{"price":100})
    monkeypatch.setattr(debate.chat,"_call_llm_stream",lambda *a,**k:Response())
    events=list(debate.run_debate_stream({},"600519"))
    assert all(event.get("failed") for event in events if event["type"]=="stage_done")
    assert events[-1]["stages"]==[]


def test_debate_parser_streams_chinese_and_requires_successful_terminal():
    class Response:
        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"第一段"}}]}'.encode()
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
            yield b'data: [DONE]'
    assert list(debate._iter_debate_deltas(Response()))[0]["content"]=="第一段"


def test_disconnect_does_not_block_event_loop_on_response_close(monkeypatch):
    monkeypatch.setattr(app.glm_config,"load_glm_config",lambda:{"apiKey":"test"})
    close_started,release_close=Event(),Event()
    class Response:
        def close(self):
            close_started.set()
            release_close.wait(2)
    def fake(config,code,rounds,control):
        control.bind(Response())
        yield {"type":"status"}
    monkeypatch.setattr(debate,"run_debate_stream",fake)
    async def exercise():
        response=app.debate(app.DebateReq(code="600519"))
        await anext(response.body_iterator)
        loop=asyncio.get_running_loop()
        start=loop.time()
        await response.body_iterator.aclose()
        await asyncio.sleep(0)
        assert loop.time()-start < 0.5
    try:
        asyncio.run(exercise())
        assert close_started.wait(1)
    finally:
        release_close.set()
