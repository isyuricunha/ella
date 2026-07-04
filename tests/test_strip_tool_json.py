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


class TestStripXmlToolCallTags:
    """Tests for XML-style hallucinated tool-call tag stripping."""

    def test_strips_tool_call_open_tag(self):
        lt, gt = chr(60), chr(62)
        text = "Here is a plan." + "\n" + lt + "tool_call" + gt + "shell"
        result = agent._strip_tool_call_json(text)
        assert result == "Here is a plan."

    def test_strips_tool_call_close_tag(self):
        lt, gt = chr(60), chr(62)
        text = "Good content." + "\n" + lt + "/tool_call" + gt
        result = agent._strip_tool_call_json(text)
        assert result == "Good content."

    def test_strips_command_tag(self):
        lt, gt = chr(60), chr(62)
        text = "I will fix it." + "\n" + lt + "command" + gt + "\nls -la" + "\n" + lt + "/command" + gt
        result = agent._strip_tool_call_json(text)
        assert result == "I will fix it."

    def test_strips_arg_key_tag(self):
        lt, gt = chr(60), chr(62)
        text = "Plan text." + "\n" + lt + "arg_key" + gt + "command" + lt + "/arg_key" + gt
        result = agent._strip_tool_call_json(text)
        assert result == "Plan text."

    def test_strips_maid_tag(self):
        lt, gt = chr(60), chr(62)
        text = "Real output." + "\n" + lt + "maid" + gt + lt + "/maid" + gt
        result = agent._strip_tool_call_json(text)
        assert result == "Real output."

    def test_strips_think_close_tag(self):
        lt, gt = chr(60), chr(62)
        text = "My plan." + "\n" + lt + "/think" + gt
        result = agent._strip_tool_call_json(text)
        assert result == "My plan."

    def test_strips_result_tag(self):
        lt, gt = chr(60), chr(62)
        text = "Analysis." + "\n" + lt + "/result" + gt
        result = agent._strip_tool_call_json(text)
        assert result == "Analysis."

    def test_preserves_text_before_tags(self):
        lt, gt = chr(60), chr(62)
        text = (
            "I will help you create a plan for adding a CONTRIBUTING.md file!"
            " Let me first explore the repository to understand the project structure"
            " and then create a comprehensive plan."
            "\n" + lt + "tool_call" + gt + "shell"
            "\n" + lt + "arg_key" + gt + "command"
            "\n" + lt + "arg_value" + gt + "find . -type f"
            + lt + "/arg_value" + gt
            + lt + "/arg_key" + gt
        )
        result = agent._strip_tool_call_json(text)
        assert "comprehensive plan" in result
        assert "tool_call" not in result
        assert "arg_key" not in result

    def test_strips_shell_code_fence(self):
        text = "Here is the plan.\n```shell\nfind . -type f\n```"
        result = agent._strip_tool_call_json(text)
        assert result == "Here is the plan."

    def test_strips_bash_code_fence(self):
        text = "My analysis.\n```bash\necho hello\n```"
        result = agent._strip_tool_call_json(text)
        assert result == "My analysis."

    def test_preserves_regular_text_fence(self):
        text = "Here is code.\n```python\nx = 1\n```"
        result = agent._strip_tool_call_json(text)
        assert "python" in result
        assert "x = 1" in result
