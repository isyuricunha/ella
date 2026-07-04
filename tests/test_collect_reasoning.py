"""Tests for collect_ai_choices reasoning token handling."""

import importlib.util
from pathlib import Path


def _load_agent_module():
    agent_path = Path(__file__).resolve().parent.parent / ".ella" / "agent.py"
    spec = importlib.util.spec_from_file_location("ella_agent", agent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = _load_agent_module()
Ella = agent.Ella


def _collect(chunk: dict) -> tuple[list[str], list[str]]:
    """Run collect_ai_choices on a single SSE chunk and return (content, reasoning)."""
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    active_tool_calls: dict[str, dict] = {}
    index_to_id: dict[int, str] = {}
    Ella.collect_ai_choices(
        chunk, content_parts, reasoning_parts, active_tool_calls, index_to_id
    )
    return content_parts, reasoning_parts


class TestCollectReasoning:
    def test_collects_delta_reasoning(self):
        chunk = {"choices": [{"delta": {"reasoning": "Let me think"}}]}
        content, reasoning = _collect(chunk)
        assert content == []
        assert reasoning == ["Let me think"]

    def test_collects_delta_reasoning_content(self):
        chunk = {"choices": [{"delta": {"reasoning_content": "DeepSeek style"}}]}
        content, reasoning = _collect(chunk)
        assert content == []
        assert reasoning == ["DeepSeek style"]

    def test_collects_message_reasoning(self):
        chunk = {"choices": [{"message": {"reasoning": "Non-streaming reasoning"}}]}
        content, reasoning = _collect(chunk)
        assert content == []
        assert reasoning == ["Non-streaming reasoning"]

    def test_collects_message_reasoning_content(self):
        chunk = {"choices": [{"message": {"reasoning_content": "Non-streaming DS"}}]}
        content, reasoning = _collect(chunk)
        assert content == []
        assert reasoning == ["Non-streaming DS"]

    def test_reasoning_never_in_content(self):
        chunk = {"choices": [{"delta": {"reasoning": "thinking", "content": "answer"}}]}
        content, reasoning = _collect(chunk)
        assert content == ["answer"]
        assert reasoning == ["thinking"]

    def test_no_reasoning_field(self):
        chunk = {"choices": [{"delta": {"content": "just content"}}]}
        content, reasoning = _collect(chunk)
        assert content == ["just content"]
        assert reasoning == []

    def test_accumulates_reasoning_across_chunks(self):
        chunks = [
            {"choices": [{"delta": {"reasoning": "Part 1. "}}]},
            {"choices": [{"delta": {"reasoning": "Part 2."}}]},
        ]
        all_content: list[str] = []
        all_reasoning: list[str] = []
        for chunk in chunks:
            c, r = _collect(chunk)
            all_content.extend(c)
            all_reasoning.extend(r)
        assert "".join(all_content) == ""
        assert "".join(all_reasoning) == "Part 1. Part 2."

    def test_mixed_reasoning_and_content_chunks(self):
        chunks = [
            {"choices": [{"delta": {"reasoning": "Analyzing"}}]},
            {"choices": [{"delta": {"reasoning": " the code"}}]},
            {"choices": [{"delta": {"content": "Here is "}}]},
            {"choices": [{"delta": {"content": "my answer"}}]},
        ]
        all_content: list[str] = []
        all_reasoning: list[str] = []
        for chunk in chunks:
            c, r = _collect(chunk)
            all_content.extend(c)
            all_reasoning.extend(r)
        assert "".join(all_content) == "Here is my answer"
        assert "".join(all_reasoning) == "Analyzing the code"

    def test_empty_delta(self):
        chunk = {"choices": [{"delta": {}}]}
        content, reasoning = _collect(chunk)
        assert content == []
        assert reasoning == []

    def test_no_choices(self):
        chunk = {}
        content, reasoning = _collect(chunk)
        assert content == []
        assert reasoning == []

    def test_tool_calls_still_work_with_reasoning(self):
        chunk = {
            "choices": [
                {
                    "delta": {
                        "reasoning": "I need to read a file",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "index": 0,
                                "type": "function",
                                "function": {"name": "read_file", "arguments": '{"filepath": "test.py"}'},
                            }
                        ],
                    }
                }
            ]
        }
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        active_tool_calls: dict[str, dict] = {}
        index_to_id: dict[int, str] = {}
        Ella.collect_ai_choices(
            chunk, content_parts, reasoning_parts, active_tool_calls, index_to_id
        )
        assert reasoning_parts == ["I need to read a file"]
        assert len(active_tool_calls) == 1
        assert active_tool_calls["call_1"]["function"]["name"] == "read_file"
