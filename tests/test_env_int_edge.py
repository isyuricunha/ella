"""Test env_int edge cases for zero and negative values."""
import os
import pytest
import importlib.util

@pytest.fixture
def env_int_fn(monkeypatch):
    """Load env_int from agent.py without importing the whole module."""
    spec = importlib.util.spec_from_file_location(
        "agent", ".ella/agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.env_int


def test_env_int_zero_is_valid(env_int_fn, monkeypatch):
    """ELLA_MAX_ATTEMPTS=0 should be accepted as a valid value."""
    monkeypatch.setenv("TEST_VAR", "0")
    assert env_int_fn("TEST_VAR", default=42) == 0


def test_env_int_negative_rejected(env_int_fn, monkeypatch):
    """Negative values should fall back to default."""
    monkeypatch.setenv("TEST_VAR", "-1")
    assert env_int_fn("TEST_VAR", default=42) == 42
