"""Tests for _strip_tool_call_json helper."""


def _load_agent_module():
    import importlib.util
    from pathlib import Path

    agent_path = Path(__file__).resolve().parent.parent / ".ella" / "agent.py"
    spec = importlib.util.spec_from_file_location("ella_agent", agent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = _load_agent_module()


class TestStripToolCallJson:
    def test_strips_single_tool_json(self):
        result = agent._strip_tool_call_json(
            'Some text\n{"tool": "read_file", "path": "package.json"}'
        )
        assert result == "Some text"

    def test_strips_multiple_tool_json(self):
        result = agent._strip_tool_call_json(
            'I will check\n{"tool": "grep", "pattern": "foo"}\n{"tool": "read_file"}'
        )
        assert "tool" not in result

    def test_preserves_plain_text(self):
        result = agent._strip_tool_call_json("Just plain text, no JSON")
        assert result == "Just plain text, no JSON"

    def test_preserves_review_json(self):
        summary = '{"summary": "Good code", "comments": [{"path": "a.py", "line": 1, "body": "ok"}]}'
        result = agent._strip_tool_call_json(summary)
        assert result == summary

    def test_empty_string(self):
        assert agent._strip_tool_call_json("") == "I could not generate a response. Please try rephrasing your request."

    def test_strips_all_tool_json_lines(self):
        text = '{"tool": "grep", "pattern": "foo"}\n{"tool": "read_file", "path": "bar"}'
        result = agent._strip_tool_call_json(text)
        assert "tool" not in result
