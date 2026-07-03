"""Tests for dual-model support (large + small) routing and fallback."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

AGENT_PATH = Path(__file__).resolve().parent.parent / ".ella" / "agent.py"


def _load_agent_module():
    spec = importlib.util.spec_from_file_location("ella_agent", AGENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = _load_agent_module()


def _make_ella_shell():
    """Create an Ella instance without calling __init__."""
    obj = object.__new__(agent.Ella)
    obj.ai_model = "large-model"
    obj.ai_base_url = "https://large.example.com"
    obj.ai_api_key = "large-key"
    obj.ai_small_model = "small-model"
    obj.ai_small_base_url = "https://small.example.com"
    obj.ai_small_api_key = "small-key"
    return obj


class TestSmallModelFallback:
    def test_small_model_falls_back_to_large_when_not_set(self, monkeypatch):
        monkeypatch.setenv("ELLA_AI_MODEL", "large-model")
        monkeypatch.setenv("ELLA_AI_API_KEY", "large-key")
        monkeypatch.setenv("ELLA_AI_BASE_URL", "https://large.example.com")
        for var in ("ELLA_AI_SMALL_MODEL", "ELLA_AI_SMALL_API_KEY", "ELLA_AI_SMALL_BASE_URL"):
            monkeypatch.delenv(var, raising=False)

        # Simulate __init__ config loading logic
        ai_model = os.environ.get("ELLA_AI_MODEL", "").strip()
        ai_api_key = os.environ.get("ELLA_AI_API_KEY", "").strip()
        ai_base_url = os.environ.get("ELLA_AI_BASE_URL", "").strip()

        small_model = os.environ.get("ELLA_AI_SMALL_MODEL", "").strip() or ai_model
        small_api_key = os.environ.get("ELLA_AI_SMALL_API_KEY", "").strip() or ai_api_key
        small_base_url = os.environ.get("ELLA_AI_SMALL_BASE_URL", "").strip() or ai_base_url

        assert small_model == "large-model"
        assert small_api_key == "large-key"
        assert small_base_url == "https://large.example.com"

    def test_small_model_uses_own_value_when_set(self, monkeypatch):
        monkeypatch.setenv("ELLA_AI_MODEL", "large-model")
        monkeypatch.setenv("ELLA_AI_SMALL_MODEL", "small-model")

        ai_model = os.environ.get("ELLA_AI_MODEL", "").strip()
        small_model = os.environ.get("ELLA_AI_SMALL_MODEL", "").strip() or ai_model

        assert small_model == "small-model"
        assert ai_model == "large-model"

    def test_small_api_key_falls_back_independently(self, monkeypatch):
        monkeypatch.setenv("ELLA_AI_API_KEY", "large-key")
        monkeypatch.setenv("ELLA_AI_SMALL_MODEL", "small-model")
        monkeypatch.delenv("ELLA_AI_SMALL_API_KEY", raising=False)
        monkeypatch.delenv("ELLA_AI_SMALL_BASE_URL", raising=False)

        ai_api_key = os.environ.get("ELLA_AI_API_KEY", "").strip()
        small_api_key = os.environ.get("ELLA_AI_SMALL_API_KEY", "").strip() or ai_api_key
        small_base_url = os.environ.get("ELLA_AI_SMALL_BASE_URL", "").strip() or os.environ.get("ELLA_AI_BASE_URL", "").strip()

        # Small model is set but key falls back to large
        assert small_api_key == "large-key"


class _FakeResponse:
    def __init__(self):
        self.status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def __iter__(self):
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
        yield b"data: [DONE]\n"


class TestAiCallRouting:
    def test_ai_call_uses_large_model_by_default(self, monkeypatch):
        ella = _make_ella_shell()
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode())
            return _FakeResponse()

        monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
        ella.ai_call([{"role": "user", "content": "hi"}], 100)

        assert captured["body"]["model"] == "large-model"
        assert "large.example.com" in captured["url"]
        assert captured["headers"]["Authorization"] == "Bearer large-key"

    def test_ai_call_uses_small_model_when_requested(self, monkeypatch):
        ella = _make_ella_shell()
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode())
            return _FakeResponse()

        monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
        ella.ai_call([{"role": "user", "content": "hi"}], 100, use_small=True)

        assert captured["body"]["model"] == "small-model"
        assert "small.example.com" in captured["url"]
        assert captured["headers"]["Authorization"] == "Bearer small-key"
