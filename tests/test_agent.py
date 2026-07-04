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

    def test_git_push_blocked(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": "git push origin main"}))
        assert "blocked" in result.lower()

    def test_git_reset_hard_blocked(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": "git reset --hard HEAD~1"}))
        assert "blocked" in result.lower()

    def test_git_checkout_dot_blocked(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": "git checkout ."}))
        assert "blocked" in result.lower()

    def test_empty_command_rejected(self):
        ella = _make_ella_shell()
        result = ella.execute_tool("run_terminal_command", json.dumps({"command": ""}))
        assert "required" in result.lower()


# --- __init__ defensive behavior ---


class TestInitDefaultBranch:
    def test_missing_repository_key_does_not_crash(self, monkeypatch, tmp_path):
        event = {}  # no "repository" key at all
        p = tmp_path / "event.json"
        p.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        obj = agent.Ella()
        assert obj.default_branch == "main"

    def test_missing_default_branch_key_falls_back(self, monkeypatch, tmp_path):
        event = {"repository": {}}  # repository present but no default_branch
        p = tmp_path / "event.json"
        p.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        obj = agent.Ella()
        assert obj.default_branch == "main"

    def test_default_branch_present(self, monkeypatch, tmp_path):
        event = {"repository": {"default_branch": "develop"}}
        p = tmp_path / "event.json"
        p.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        obj = agent.Ella()
        assert obj.default_branch == "develop"


# --- quote mode registration ---


class TestQuoteModeRegistration:
    def test_quote_in_max_tokens(self):
        assert "quote" in agent.MAX_TOKENS
        assert agent.MAX_TOKENS["quote"] >= 60

    def test_quote_default_prompt_in_defaults(self, monkeypatch, tmp_path):
        event = {"repository": {"default_branch": "main"}}
        p = tmp_path / "event.json"
        p.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
        obj = agent.Ella()
        obj.parse_command()
        assert obj.mode == "quote"
        assert "quote" in obj.prompt.lower()

    def test_workflow_dispatch_routes_to_quote(self, monkeypatch, tmp_path):
        event = {"repository": {"default_branch": "main"}}
        p = tmp_path / "event.json"
        p.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
        obj = agent.Ella()
        obj.parse_command()
        assert obj.mode == "quote"


# --- _handle_quote ---


def _make_quote_shell(monkeypatch, tmp_path, readme_text, model_output):
    obj = object.__new__(agent.Ella)
    obj.mode = "quote"
    obj.prompt = "Generate a short uplifting quote of the week for a developer's GitHub profile README."
    obj.repo = "isyuricunha/isyuricunha"
    obj.default_branch = "main"
    obj.commit_name = "Ella Mizuki"
    obj.commit_email = "290269138+ella-mizuki[bot]@users.noreply.github.com"
    obj.yuri_name = ""
    obj.yuri_email = ""
    obj.issue_number = -1
    obj.comment_id = 0
    obj.ai_base_url = "https://example.invalid"
    obj.ai_model = "m"
    obj.ai_api_key = "k"
    obj.ai_small_model = "m"
    obj.ai_small_base_url = "https://example.invalid"
    obj.ai_small_api_key = "k"
    (tmp_path / "README.md").write_text(readme_text)
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_git(args, *, check=True):
        calls.append(("git", args))
        if args[:2] == ["ls-files", "--modified"]:
            return "README.md"
        return ""

    def fake_ai_call(messages, max_tokens, tools=None, use_small=False):
        calls.append(("ai_call", use_small))
        return model_output, []

    monkeypatch.setattr(agent, "git", fake_git)
    monkeypatch.setattr(obj, "ai_call", fake_ai_call)
    obj._calls = calls
    return obj


class TestHandleQuote:
    def test_writes_quote_and_commits(self, monkeypatch, tmp_path):
        readme = "hello\n\n**a sentence to brighten your day:**<br>\n    old quote\n\n"
        obj = _make_quote_shell(monkeypatch, tmp_path, readme, "do the thing you fear")
        obj._handle_quote()
        new_readme = (tmp_path / "README.md").read_text()
        assert "do the thing you fear" in new_readme
        assert "old quote" not in new_readme
        git_args = [a for _, args in obj._calls if _ == "git" for a in args]
        assert "commit" in git_args
        assert "push" in git_args

    def test_no_commit_on_ai_failure(self, monkeypatch, tmp_path):
        readme = "hello\n\n**a sentence to brighten your day:**<br>\n    old quote\n\n"
        obj = _make_quote_shell(monkeypatch, tmp_path, readme, "irrelevant")

        def boom(*a, **k):
            raise RuntimeError("api down")
        monkeypatch.setattr(obj, "ai_call", boom)
        obj._handle_quote()
        assert "old quote" in (tmp_path / "README.md").read_text()
        assert not any(args[0] == "commit" for _, args in obj._calls if _ == "git")

    def test_no_commit_on_empty_quote(self, monkeypatch, tmp_path):
        readme = "hello\n\n**a sentence to brighten your day:**<br>\n    old quote\n\n"
        obj = _make_quote_shell(monkeypatch, tmp_path, readme, "   \n\n")
        obj._handle_quote()
        assert "old quote" in (tmp_path / "README.md").read_text()
        assert not any(args[0] == "commit" for _, args in obj._calls if _ == "git")


class TestSanitizeQuote:
    def test_strips_fences(self):
        assert agent.Ella._sanitize_quote("```\ndo the thing\n```") == "do the thing"

    def test_strips_fences_with_lang(self):
        assert agent.Ella._sanitize_quote("```text\nkeep going\n```") == "keep going"

    def test_strips_quotes(self):
        assert agent.Ella._sanitize_quote('"do the thing"') == "do the thing"

    def test_takes_first_line(self):
        assert agent.Ella._sanitize_quote("first line\nsecond line") == "first line"

    def test_caps_length(self):
        long = "word " * 40
        out = agent.Ella._sanitize_quote(long)
        assert len(out) <= 140 and out.endswith("...")

    def test_empty(self):
        assert agent.Ella._sanitize_quote("   \n\n") == ""

    def test_lowercases_output(self):
        assert agent.Ella._sanitize_quote("Every Line Of Code Is A Step") == "every line of code is a step"

    def test_strips_bold(self):
        assert agent.Ella._sanitize_quote("**bold text**") == "bold text"

    def test_strips_italic(self):
        assert agent.Ella._sanitize_quote("*italic text*") == "italic text"

    def test_strips_bold_underscore(self):
        assert agent.Ella._sanitize_quote("__bold text__") == "bold text"

    def test_strips_italic_underscore(self):
        assert agent.Ella._sanitize_quote("_italic text_") == "italic text"

    def test_strips_bold_italic(self):
        assert agent.Ella._sanitize_quote("***bold italic***") == "bold italic"

    def test_preserves_underscore_in_words(self):
        assert agent.Ella._sanitize_quote("text with_underscore") == "text with_underscore"

    def test_strips_mixed_markdown(self):
        assert agent.Ella._sanitize_quote("mixed *italic* and **bold** end") == "mixed italic and bold end"



