from route_policy import allowed_tools, policy_for
from session_store import Principal


def test_private_legacy_endpoints_are_owner_only():
    for method, path in [("GET", "/api/portfolio"), ("POST", "/api/reflect"), ("GET", "/api/myreports/file/report-id")]:
        assert policy_for(method, path) == "owner"
    assert policy_for("POST", "/api/not-registered") == "deny"


def test_market_reads_need_identity_and_tools_are_scoped():
    assert policy_for("GET", "/api/quote") == "authenticated"
    assert policy_for("GET", "/api/health") == "public"
    assert "query_quote" in allowed_tools(Principal("g", "guest"))
    assert "query_portfolio" not in allowed_tools(Principal("g", "guest"))


def test_run_event_stream_requires_identity():
    assert policy_for("GET", "/api/runs/run-id/events") == "authenticated"


def test_scoped_tool_denial_happens_before_handler(monkeypatch):
    import chat
    called = []
    monkeypatch.setattr(chat, "_exec_tool", lambda name, args: called.append(name) or {"ok": True})
    assert chat._exec_scoped_tool("query_financials", {}, {"query_quote"})["error"]
    assert called == []
