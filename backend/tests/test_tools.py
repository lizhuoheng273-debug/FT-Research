import time

import tools


def test_slow_tool_times_out_without_blocking_worker(monkeypatch):
    def slow(_args):
        time.sleep(0.2)
        return {"status": "ok"}

    monkeypatch.setitem(tools._HANDLERS, "slow_test", slow)
    started = time.monotonic()
    result = tools.execute_scoped_tool("slow_test", {}, None, timeout_seconds=0.02)

    assert time.monotonic() - started < 0.12
    assert result["status"] == "unavailable"
    assert "20" in result["data_gap"]
