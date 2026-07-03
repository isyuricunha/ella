"""Test env_int handles edge cases correctly.

env_int should:
- Return the default when env var is missing or empty
- Return the parsed value for any non-negative integer (including 0)
- Return the default for negative values
- Return the default for non-integer values
"""
import importlib.util
import pytest

@pytest.fixture
def utils():
    spec = importlib.util.spec_from_file_location("agent", ".ella/agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_env_int_positive(utils, monkeypatch):
    monkeypatch.setenv("TEST_VAR", "42")
    assert utils.env_int("TEST_VAR", default=10) == 42


def test_env_int_zero(utils, monkeypatch):
    """Zero is a valid non-negative integer and should be returned, not the default."""
    monkeypatch.setenv("TEST_VAR", "0")
    assert utils.env_int("TEST_VAR", default=10) == 0


def test_env_int_negative(utils, monkeypatch):
    monkeypatch.setenv("TEST_VAR", "-5")
    assert utils.env_int("TEST_VAR", default=10) == 10


def test_env_int_missing(utils, monkeypatch):
    monkeypatch.delenv("TEST_VAR", raising=False)
    assert utils.env_int("TEST_VAR", default=10) == 10


def test_env_int_non_numeric(utils, monkeypatch):
    monkeypatch.setenv("TEST_VAR", "abc")
    assert utils.env_int("TEST_VAR", default=10) == 10
