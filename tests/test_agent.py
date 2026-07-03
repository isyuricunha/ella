"""Unit tests for Ella agent pure functions and methods.

These tests exercise the standalone helper functions and the Ella
methods that do not require a live GitHub environment.
"""

import importlib.util
import json
import os
import sys
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
    """Create an Ella instance without calling __init__ (no GITHUB_EVENT_PATH needed)."""
    obj = object.__new__(agent.Ella)
    obj.mode = "fix"
    obj.prompt = "test prompt"
    obj.allowed_files = []
    obj.final_summary = ""
    obj.feedback = ""
    obj.extra_context = ""
    obj.issue_info = None
    obj.pr_info = None
    obj.issue_number = 42
    obj.yuri_name = ""
    obj.yuri_email = ""
    return obj


# --- env_int ---


class TestEnvInt:
    def test_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("ELLA_TEST_VAR", raising=False)
        assert agent.env_int("ELLA_TEST_VAR", 99) == 99

    def test_default_when_empty(self, monkeypatch):
        monkeypatch.setenv("ELLA_TEST_VAR", "")
        assert agent.env_int("ELLA_TEST_VAR", 99) == 99

    def test_default_when_non_numeric(self, monkeypatch):
        monkeypatch.setenv("ELLA_TEST_VAR", "abc")
        assert agent.env_int("ELLA_TEST_VAR", 99) == 99

    def test_default_when_zero_or_negative(self, monkeypatch):
        monkeypatch.setenv("ELLA_TEST_VAR", "0")
        assert agent.env_int("ELLA_TEST_VAR", 99) == 99
        monkeypatch.setenv("ELLA_TEST_VAR", "-5")
        assert agent.env_int("ELLA_TEST_VAR", 99) == 99

    def test_valid_value(self, monkeypatch):
        monkeypatch.setenv("ELLA_TEST_VAR", "42")
        assert agent.env_int("ELLA_TEST_VAR", 99) == 42


# --- scrub_secrets ---


class TestScrubSecrets:
    def test_redacts_known_env_secret(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "ghp_" + "a" * 36)
        result = agent.scrub_secrets("my token is ghp_" + "a" * 36)
        assert "REDACTED" in result
        assert "ghp_" + "a" * 36 not in result

    def test_redacts_pat_pattern(self):
        result = agent.scrub_secrets("found ghp_" + "b" * 36 + " here")
        assert "REDACTED" in result
        assert "ghp_" + "b" * 36 not in result

    def test_redacts_finegrained_token_pattern(self):
        result = agent.scrub_secrets("found ghs_" + "d" * 36 + " here")
        assert "REDACTED" in result

    def test_no_secret_passthrough(self):
        assert agent.scrub_secrets("nothing to redact") == "nothing to redact"

    def test_non_string_input(self):
        assert agent.scrub_secrets(123) == 123


# --- safe_rel_path ---


class TestSafeRelPath:
    def test_simple_relative(self):
        assert agent.safe_rel_path("src/main.py") is True

    def test_absolute_rejected(self):
        assert agent.safe_rel_path("/etc/passwd") is False

    def test_parent_traversal_rejected(self):
        assert agent.safe_rel_path("../secret") is False
        assert agent.safe_rel_path("foo/../../bar") is False

    def test_git_directory_rejected(self):
        assert agent.safe_rel_path(".git/config") is False

    def test_empty_rejected(self):
        assert agent.safe_rel_path("") is False
        assert agent.safe_rel_path("   ") is False


# --- is_ignored ---


class TestIsIgnored:
    def test_node_modules(self):
        assert agent.is_ignored("src/node_modules/react/index.js", agent.DEFAULT_IGNORE) is True

    def test_env_file(self):
        assert agent.is_ignored(".env", agent.DEFAULT_IGNORE) is True

    def test_env_subdir(self):
        assert agent.is_ignored("config/.env.production", agent.DEFAULT_IGNORE) is True

    def test_normal_file_not_ignored(self):
        assert agent.is_ignored("src/app/page.tsx", agent.DEFAULT_IGNORE) is False

    def test_lockfile_ignored(self):
        assert agent.is_ignored("pnpm-lock.yaml", agent.DEFAULT_IGNORE) is True

    def test_custom_pattern(self):
        patterns = ["**/vendor/**"]
        assert agent.is_ignored("pkg/vendor/lib.go", patterns) is True
        assert agent.is_ignored("src/main.go", patterns) is False


# --- parse_jsonish ---


class TestParseJsonish:
    def test_clean_json(self):
        assert agent.parse_jsonish('{"key": "value"}') == {"key": "value"}

    def test_json_in_code_fence(self):
        result = agent.parse_jsonish('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_in_plain_code_fence(self):
        result = agent.parse_jsonish('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_embedded_in_text(self):
        result = agent.parse_jsonish('Here is the result:\n{"labels": ["bug"]}\nDone.')
        assert result == {"labels": ["bug"]}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            agent.parse_jsonish("not json at all")


# --- parse_markdown_files ---


class TestParseMarkdownFiles:
    def test_single_page(self):
        text = "---FILENAME: Home.md---\n# Home\nWelcome!"
        result = agent.parse_markdown_files(text)
        assert "Home.md" in result
        assert "# Home" in result["Home.md"]

    def test_multiple_pages(self):
        text = (
            "---FILENAME: Home.md---\n# Home\n\n"
            "---FILENAME: Setup.md---\n# Setup\nInstall stuff"
        )
        result = agent.parse_markdown_files(text)
        assert set(result.keys()) == {"Home.md", "Setup.md"}
        assert "Install stuff" in result["Setup.md"]

    def test_fallback_no_delimiters(self):
        result = agent.parse_markdown_files("Just some text without delimiters")
        assert "Home.md" in result
        assert "Just some text" in result["Home.md"]


# --- compute_max_attempts ---


class TestComputeMaxAttempts:
    def test_default_with_no_files(self, monkeypatch):
        monkeypatch.delenv("ELLA_MAX_ATTEMPTS", raising=False)
        ella = _make_ella_shell()
        ella.allowed_files = []
        assert ella.compute_max_attempts() == 25

    def test_scales_with_allowed_files(self, monkeypatch):
        monkeypatch.delenv("ELLA_MAX_ATTEMPTS", raising=False)
        ella = _make_ella_shell()
        ella.allowed_files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
        assert ella.compute_max_attempts() == 25 + 2 * 5

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ELLA_MAX_ATTEMPTS", "50")
        ella = _make_ella_shell()
        ella.allowed_files = ["a.py"]
        assert ella.compute_max_attempts() == 50

    def test_cap_at_300(self, monkeypatch):
        monkeypatch.setenv("ELLA_MAX_ATTEMPTS", "999")
        ella = _make_ella_shell()
        assert ella.compute_max_attempts() == 300


# --- infer_commit_type ---


class TestInferCommitType:
    def test_docs_only(self):
        ella = _make_ella_shell()
        result = ella.infer_commit_type(["README.md", "docs/guide.md"])
        assert result == ("docs", None)

    def test_ci_only(self):
        ella = _make_ella_shell()
        result = ella.infer_commit_type([".github/workflows/ci.yml"])
        assert result == ("ci", None)

    def test_test_only(self):
        ella = _make_ella_shell()
        result = ella.infer_commit_type(["tests/test_foo.py", "src/foo.test.ts"])
        assert result == ("test", None)

    def test_dependency_update(self):
        ella = _make_ella_shell()
        result = ella.infer_commit_type(["package.json", "pnpm-lock.yaml"])
        assert result[0] == "chore"
        assert result[1] == "deps"

    def test_mixed_defaults_to_fix(self):
        ella = _make_ella_shell()
        result = ella.infer_commit_type(["src/app.tsx", "README.md"])
        assert result == ("fix", None)

    def test_empty_list(self):
        ella = _make_ella_shell()
        assert ella.infer_commit_type([]) == ("chore", None)


# --- blocked command guard ---


class TestBlockedCommands:
    def test_recursive_rm_blocked(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": "rm -rf /"}))
        assert "blocked" in result.lower()

    def test_force_push_blocked(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": "git push --force origin main"}))
        assert "blocked" in result.lower()

    def test_safe_command_allowed(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": "echo hello"}))
        assert "blocked" not in result.lower()

    def test_empty_command_rejected(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": ""}))
        assert "required" in result.lower()
