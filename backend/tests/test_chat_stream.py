import threading
import time

import chat


def _cfg():
    return {"baseURL": "http://127.0.0.1", "apiKey": "key", "model": "model"}


def _two_tool_round_then_answer(monkeypatch):
    rounds = [
        [{"tool_calls": [
            {"index": 0, "id": "call-a", "function": {"name": "query_quote", "arguments": '{"codes":["600519"]}'}},
            {"index": 1, "id": "call-b", "function": {"name": "query_news", "arguments": '{"code":"600519"}'}},
        ]}],
        [{"content": "回答"}],
    ]
    state = {"round": 0}
    monkeypatch.setattr(chat, "_call_llm_stream", lambda *args, **kwargs: None)

    def fake_iter(_response):
        current = rounds[state["round"]]
        state["round"] += 1
        yield from current

    monkeypatch.setattr(chat, "_iter_sse_deltas", fake_iter)


def test_independent_tools_start_in_parallel_and_emit_progress(monkeypatch):
    _two_tool_round_then_answer(monkeypatch)
    starts = []
    barrier = threading.Barrier(2)

    def fake_tool(name, args, allowed, timeout_seconds=20.0):
        starts.append(time.monotonic())
        barrier.wait(timeout=0.5)
        return {"status": "ok", "tool": name}

    monkeypatch.setattr(chat, "execute_scoped_tool", fake_tool)
    events = list(chat.run_chat_stream(_cfg(), [{"role": "user", "content": "测试"}]))

    assert len(starts) == 2 and abs(starts[0] - starts[1]) < 0.05
    assert any(e["type"] == "progress" and e["payload"]["phase"] == "tool" for e in events)
    assert events[-1]["type"] == "done"


def test_tool_timeout_emits_terminal_progress_and_continues_answer(monkeypatch):
    _two_tool_round_then_answer(monkeypatch)
    monkeypatch.setattr(
        chat,
        "execute_scoped_tool",
        lambda *args, **kwargs: {"status": "unavailable", "data_gap": "数据源超时"},
    )

    events = list(chat.run_chat_stream(_cfg(), [{"role": "user", "content": "测试"}]))
    progress = [event["payload"]["status"] for event in events if event["type"] == "progress"]

    assert "running" in progress
    assert "timeout" in progress
    assert any(event["type"] == "delta" and event["text"] == "回答" for event in events)
    assert events[-1]["type"] == "done"
