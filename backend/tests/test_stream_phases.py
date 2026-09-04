import unittest
from unittest.mock import patch
import chat

class StreamPhaseTests(unittest.TestCase):
    def test_reasoning_is_reported_without_disclosing_reasoning_text(self):
        deltas = [{"reasoning_content": "PRIVATE_REASONS"}, {"reasoning_content": "MORE"}, {"content": "ANSWER"}]
        with patch.object(chat, "_call_llm_stream", return_value=None), patch.object(chat, "_iter_sse_deltas", side_effect=lambda _: iter(deltas)):
            events = list(chat.run_chat_stream({}, [{"role": "user", "content": "test"}]))
        self.assertTrue(any(e.get("payload", {}).get("phase") == "reasoning" for e in events))
        self.assertNotIn("PRIVATE_REASONS", str(events))
        self.assertEqual([e["text"] for e in events if e["type"] == "delta"], ["ANSWER"])

    def test_tool_argument_stream_reports_planning_before_tool_execution(self):
        rounds = iter([[{"tool_calls": [{"index": 0, "id": "a", "function": {"name": "query_quote", "arguments": "{}"}}]}], [{"content": "ANSWER"}]])
        with patch.object(chat, "_call_llm_stream", return_value=None), patch.object(chat, "_iter_sse_deltas", side_effect=lambda _: iter(next(rounds))), patch.object(chat, "execute_scoped_tool", return_value={}):
            events = list(chat.run_chat_stream({}, [{"role": "user", "content": "test"}]))
        phases = [e.get("payload", {}).get("phase") for e in events if e["type"] == "progress"]
        self.assertIn("planning", phases)
        self.assertLess(phases.index("planning"), phases.index("tool"))

if __name__ == "__main__":
    unittest.main()
