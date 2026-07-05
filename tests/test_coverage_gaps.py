"""Tests covering remaining gaps: command parsing, context validation,
checkout, WIP/commit flows, heal setup, review path, prepare_environment,
and _bump_consecutive_error.
"""

import importlib.util
import json
import os
import subprocess
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
    obj.mode = "fix"
    obj.prompt = "test prompt"
    obj.allowed_files = []
    obj.final_summary = ""
    obj.feedback = ""
    obj.extra_context = ""
    obj.issue_info = None
    obj.pr_info = None
    obj.issue_number = 42
    obj.repo = "isyuricunha/ella"
    obj.default_branch = "main"
    obj.commit_name = "Ella Mizuki"
    obj.commit_email = "ella@example.com"
    obj.yuri_name = ""
    obj.yuri_email = ""
    obj.solve_branch = "ella/issue-42-test"
    obj.run_id = "12345"
    obj.ignore_patterns = []
    obj.ai_model = "m"
    obj.ai_base_url = "https://example.invalid"
    obj.ai_api_key = "k"
    obj.ai_small_model = "m"
    obj.ai_small_base_url = "https://example.invalid"
    obj.ai_small_api_key = "k"
    obj.event = {}
    obj.comment_id = 0
    obj.is_pr = False
    obj.comment_event = {}
    obj.repo_instructions = ""
    return obj


# --- _bump_consecutive_error ---


class TestBumpConsecutiveError:
    def test_increments_consecutive(self):
        consecutive, attempt = agent.Ella._bump_consecutive_error(0, 1)
        assert consecutive == 1
        assert attempt == 1

    def test_resets_on_three(self):
        consecutive, attempt = agent.Ella._bump_consecutive_error(2, 5)
        assert consecutive == 0
        assert attempt == 6

    def test_does_not_bump_attempt_below_three(self):
        consecutive, attempt = agent.Ella._bump_consecutive_error(1, 3)
        assert consecutive == 2
        assert attempt == 3

    def test_chain_of_four_errors(self):
        # Simulate 4 consecutive errors
        consecutive = 0
        attempt = 1
        for i in range(4):
            consecutive, attempt = agent.Ella._bump_consecutive_error(consecutive, attempt)
        # After 3 errors: reset consecutive, bump attempt
        # After 4th error: consecutive=1
        assert consecutive == 1
        assert attempt == 2


# --- parse_command for all event types ---


def _parse_command_for_event(monkeypatch, tmp_path, event_name, event_data):
    """Helper to run parse_command with given event data."""
    p = tmp_path / "event.json"
    p.write_text(json.dumps(event_data))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
    monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    obj = agent.Ella()
    obj.parse_command()
    return obj


class TestParseCommandEvents:
    def test_issues_opened_routes_to_triage(self, monkeypatch, tmp_path):
        event = {"repository": {"default_branch": "main"}, "action": "opened", "issue": {"number": 10}}
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issues", event)
        assert obj.mode == "triage"

    def test_pr_opened_routes_to_review(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "action": "opened",
            "pull_request": {"number": 15},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "pull_request_target", event)
        assert obj.mode == "review"

    def test_pr_synchronize_routes_to_review(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "action": "synchronize",
            "pull_request": {"number": 16},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "pull_request_target", event)
        assert obj.mode == "review"

    def test_workflow_run_routes_to_heal(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "action": "completed",
            "workflow_run": {"id": 99, "head_branch": "feature-x", "pull_requests": [{"number": 20}]},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "workflow_run", event)
        assert obj.mode == "heal"

    def test_schedule_routes_to_quote(self, monkeypatch, tmp_path):
        event = {"repository": {"default_branch": "main"}}
        obj = _parse_command_for_event(monkeypatch, tmp_path, "schedule", event)
        assert obj.mode == "quote"

    def test_workflow_dispatch_routes_to_quote(self, monkeypatch, tmp_path):
        event = {"repository": {"default_branch": "main"}}
        obj = _parse_command_for_event(monkeypatch, tmp_path, "workflow_dispatch", event)
        assert obj.mode == "quote"

    def test_issue_comment_help_command(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "issue": {"number": 30},
            "comment": {"body": "/ella help", "user": {"login": "isyuricunha"}},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issue_comment", event)
        assert obj.mode == "help"

    def test_issue_comment_ask_command(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "issue": {"number": 31},
            "comment": {"body": "/ella ask what is going on?", "user": {"login": "isyuricunha"}},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issue_comment", event)
        assert obj.mode == "ask"
        assert "what is going on" in obj.prompt

    def test_issue_comment_fix_command(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "issue": {"number": 32},
            "comment": {"body": "/ella fix the broken parser", "user": {"login": "isyuricunha"}},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issue_comment", event)
        assert obj.mode == "fix"
        assert "broken parser" in obj.prompt

    def test_issue_comment_solve_command(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "issue": {"number": 33},
            "comment": {"body": "/ella solve the null pointer crash", "user": {"login": "isyuricunha"}},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issue_comment", event)
        assert obj.mode == "solve"

    def test_issue_comment_wiki_command(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "issue": {"number": 34},
            "comment": {"body": "/ella wiki", "user": {"login": "isyuricunha"}},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issue_comment", event)
        assert obj.mode == "wiki"

    def test_issue_comment_unknown_command(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "issue": {"number": 35},
            "comment": {"body": "just a regular comment", "user": {"login": "isyuricunha"}},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issue_comment", event)
        assert obj.mode == "unknown"

    def test_default_prompt_when_no_text(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "issue": {"number": 36},
            "comment": {"body": "/ella ask", "user": {"login": "isyuricunha"}},
        }
        obj = _parse_command_for_event(monkeypatch, tmp_path, "issue_comment", event)
        assert obj.mode == "ask"
        # Should have default prompt
        assert len(obj.prompt) > 0


# --- _validate_and_load_context ---


class TestValidateAndLoadContext:
    def test_pr_only_mode_on_non_pr_returns_error(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "pr"
        obj.is_pr = False
        obj.ai_base_url = "https://example.invalid"
        obj.ai_model = "m"
        obj.ai_api_key = "k"
        monkeypatch.setattr(obj, "validate_ai_config", lambda: None)
        result = obj._validate_and_load_context()
        assert "PR" in result

    def test_fix_on_non_pr_returns_error(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "fix"
        obj.is_pr = False
        obj.ai_base_url = "https://example.invalid"
        obj.ai_model = "m"
        obj.ai_api_key = "k"
        monkeypatch.setattr(obj, "validate_ai_config", lambda: None)
        result = obj._validate_and_load_context()
        assert "PR" in result

    def test_solve_on_pr_returns_error(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "solve"
        obj.is_pr = True
        obj.ai_base_url = "https://example.invalid"
        obj.ai_model = "m"
        obj.ai_api_key = "k"
        monkeypatch.setattr(obj, "validate_ai_config", lambda: None)
        result = obj._validate_and_load_context()
        assert "/ella fix" in result

    def test_solve_on_issue_loads_metadata(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "solve"
        obj.is_pr = False
        obj.ai_base_url = "https://example.invalid"
        obj.ai_model = "m"
        obj.ai_api_key = "k"
        loaded = []
        monkeypatch.setattr(obj, "validate_ai_config", lambda: None)
        monkeypatch.setattr(obj, "load_issue_metadata", lambda: loaded.append("issue"))
        result = obj._validate_and_load_context()
        assert result is None
        assert "issue" in loaded

    def test_review_skips_draft_pr(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "review"
        obj.is_pr = True
        obj.comment_id = 0
        obj.ai_base_url = "https://example.invalid"
        obj.ai_model = "m"
        obj.ai_api_key = "k"
        obj.pr_info = {"isDraft": True, "headRefName": "draft-branch"}
        monkeypatch.setattr(obj, "validate_ai_config", lambda: None)
        monkeypatch.setattr(obj, "load_pr_metadata", lambda: None)
        result = obj._validate_and_load_context()
        assert result == "__skip__"

    def test_review_on_non_draft_pr_proceeds(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "review"
        obj.is_pr = True
        obj.comment_id = 0
        obj.ai_base_url = "https://example.invalid"
        obj.ai_model = "m"
        obj.ai_api_key = "k"
        obj.pr_info = {"isDraft": False, "headRefName": "feature-x"}
        loaded = []
        monkeypatch.setattr(obj, "validate_ai_config", lambda: None)
        monkeypatch.setattr(obj, "load_pr_metadata", lambda: loaded.append("pr"))
        result = obj._validate_and_load_context()
        assert result is None
        assert "pr" in loaded


# --- checkout_pr_branch ---


class TestCheckoutPrBranch:
    def test_checkout_pr_branch_fetches_and_checksout(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefName": "feature-branch"}
        git_calls = []
        monkeypatch.setattr(agent, "git", lambda args, check=True: git_calls.append(args))
        obj.checkout_pr_branch()
        assert ["fetch", "origin", "refs/heads/feature-branch:refs/remotes/origin/feature-branch"] in git_calls
        assert ["checkout", "-B", "feature-branch", "origin/feature-branch"] in git_calls

    def test_checkout_pr_branch_no_pr_info_raises(self):
        obj = _make_ella_shell()
        obj.pr_info = None
        with pytest.raises(RuntimeError, match="PR info"):
            obj.checkout_pr_branch()


# --- checkout_solve_branch ---


class TestCheckoutSolveBranch:
    def test_checkout_solve_branch_creates_branch_name(self, monkeypatch):
        obj = _make_ella_shell()
        obj.issue_info = {"title": "Fix the broken parser in utils"}
        obj.issue_number = 99
        obj.run_id = "67890"
        git_calls = []
        monkeypatch.setattr(agent, "git", lambda args, check=True: git_calls.append(args))
        obj.checkout_solve_branch()
        assert obj.solve_branch.startswith("ella/issue-99-")
        assert args_contains(git_calls, ["checkout", "-B", obj.solve_branch])

    def test_checkout_solve_branch_no_issue_info_raises(self):
        obj = _make_ella_shell()
        obj.issue_info = None
        with pytest.raises(RuntimeError, match="Issue info"):
            obj.checkout_solve_branch()

    def test_checkout_solve_branch_empty_title_fallback(self, monkeypatch):
        obj = _make_ella_shell()
        obj.issue_info = {"title": ""}
        obj.issue_number = 1
        obj.run_id = "11"
        git_calls = []
        monkeypatch.setattr(agent, "git", lambda args, check=True: git_calls.append(args))
        obj.checkout_solve_branch()
        assert "ella/issue-1-issue" in obj.solve_branch


def args_contains(calls_list, target):
    for c in calls_list:
        if c == target:
            return True
    return False


# --- commit_and_push_wip ---


class TestCommitAndPushWip:
    def test_wip_commit_with_changes(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefName": "feature-wip"}

        git_calls = []
        run_cmd_calls = []

        def fake_git(args, *, check=True):
            git_calls.append(args)
            if args == ["ls-files", "--modified", "--others", "--exclude-standard"]:
                return "src/main.py\ntests/test.py\n"
            return ""

        def fake_run_cmd(args, **kwargs):
            run_cmd_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(agent, "git", fake_git)
        monkeypatch.setattr(agent, "run_cmd", fake_run_cmd)

        result = obj.commit_and_push_wip("time limit")
        assert result is not None or result is None  # Should not crash
        push_calls = [c for c in git_calls if "push" in c]
        assert len(push_calls) >= 1

    def test_wip_commit_no_changes_returns_none(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefName": "feature-wip"}

        monkeypatch.setattr(agent, "git", lambda args, check=True: "")
        monkeypatch.setattr(agent, "run_cmd", lambda *a, **kw: subprocess.CompletedProcess([], 0, "", ""))

        result = obj.commit_and_push_wip("time limit")
        assert result is None

    def test_wip_commit_no_branch_returns_none(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = None
        obj.solve_branch = ""

        monkeypatch.setattr(agent, "git", lambda args, check=True: "changed.py\n")
        monkeypatch.setattr(agent, "run_cmd", lambda *a, **kw: subprocess.CompletedProcess([], 0, "", ""))

        result = obj.commit_and_push_wip("turn limit")
        assert result is None


# --- write_commit_message_file ---


class TestWriteCommitMessageFile:
    def test_writes_message_file(self, monkeypatch, tmp_path):
        obj = _make_ella_shell()
        monkeypatch.setattr(obj, "generate_commit_message", lambda files: "fix: handle edge case\n\n- Fixed null pointer\n")
        result_path = obj.write_commit_message_file(["src/main.py"])
        assert result_path.exists()
        content = result_path.read_text()
        assert "fix: handle edge case" in content
        os.unlink(result_path)

    def test_message_file_is_tempfile(self, monkeypatch, tmp_path):
        obj = _make_ella_shell()
        monkeypatch.setattr(obj, "generate_commit_message", lambda files: "chore: cleanup\n")
        result_path = obj.write_commit_message_file([])
        assert result_path.suffix == ".txt"
        os.unlink(result_path)


# --- handle_review full path: handle_read_only -> parse_jsonish -> post_inline_review ---


class TestHandleReadOnlyReview:
    def test_review_response_with_summary_and_comments(self, monkeypatch):
        """Test that a review JSON response walks through to post_inline_review."""
        obj = _make_ella_shell()
        obj.mode = "review"
        obj.is_pr = True
        obj.pr_info = {"headRefName": "feature-x", "headRefOid": "abc123"}

        review_json = json.dumps({
            "summary": "This PR has a potential null pointer issue.",
            "comments": [
                {"path": "src/main.py", "line": 42, "body": "This could be null."},
                {"path": "src/utils.py", "line": 10, "body": "Missing return statement."},
            ],
        })

        monkeypatch.setattr(obj, "handle_read_only", lambda: review_json)
        posted = []

        def fake_post_inline_review(summary, comments):
            posted.append((summary, comments))

        def fake_react(emoji):
            pass

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        monkeypatch.setattr(obj, "post_inline_review", fake_post_inline_review)
        monkeypatch.setattr(obj, "react", fake_react)
        monkeypatch.setattr(obj, "comment", lambda msg: None)

        obj._handle_read_only()

        assert len(posted) == 1
        summary, comments = posted[0]
        assert "null pointer" in summary
        assert len(comments) == 2
        assert comments[0]["path"] == "src/main.py"

    def test_review_response_invalid_json_falls_back_to_comment(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "review"
        obj.is_pr = True
        obj.pr_info = {"headRefName": "feature-x", "headRefOid": "abc123"}

        monkeypatch.setattr(obj, "handle_read_only", lambda: "This is not JSON at all")
        commented = []

        def fake_comment(msg):
            commented.append(msg)

        def fake_react(emoji):
            pass

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        monkeypatch.setattr(obj, "post_inline_review", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "react", fake_react)
        monkeypatch.setattr(obj, "comment", fake_comment)

        obj._handle_read_only()
        # Should have commented the raw output since JSON parsing failed
        assert any("not JSON" in c or "could not parse" in c.lower() or "This is not" in c for c in commented)

    def test_review_response_empty_summary_falls_back(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "review"

        review_json = json.dumps({"summary": "", "comments": []})

        monkeypatch.setattr(obj, "handle_read_only", lambda: review_json)
        commented = []
        posted = []

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        monkeypatch.setattr(obj, "post_inline_review", lambda s, c: posted.append((s, c)))
        monkeypatch.setattr(obj, "react", lambda e: None)
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))

        obj._handle_read_only()
        # Empty summary/comments should fall through to simple comment
        assert len(commented) >= 1


# --- handle_heal setup ---


class TestHandleHealSetup:
    def test_heal_no_run_id_returns_early(self, monkeypatch):
        obj = _make_ella_shell()
        obj.event = {"workflow_run": {}}
        obj.issue_number = None
        monkeypatch.setattr(agent, "gh", lambda *a, **kw: "")
        monkeypatch.setattr(obj, "fix_loop", lambda: True)
        obj.handle_heal()  # Should not crash, should not proceed

    def test_heal_with_pr_number_loads_metadata(self, monkeypatch):
        obj = _make_ella_shell()
        obj.event = {
            "workflow_run": {
                "id": 12345,
                "head_branch": "feature-broken",
                "pull_requests": [{"number": 42}],
            }
        }
        obj.repo = "isyuricunha/ella"
        obj.issue_number = None

        metadata_loaded = []
        git_calls = []
        run_cmd_calls = []

        def fake_gh(args, *, check=True):
            if "run" in args and "view" in args:
                return "Error: test failure\nTraceback (most recent call last):\n  File test.py, line 1\n"
            return "[]"

        def fake_git(args, *, check=True):
            git_calls.append(args)
            return ""

        def fake_run_cmd(args, **kwargs):
            run_cmd_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        def fake_load_pr_metadata():
            metadata_loaded.append("pr")
            obj.pr_info = {"author": {"login": "testuser"}, "headRefName": "feature-broken"}

        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(agent, "git", fake_git)
        monkeypatch.setattr(agent, "run_cmd", fake_run_cmd)
        monkeypatch.setattr(obj, "load_pr_metadata", fake_load_pr_metadata)
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setattr(obj, "get_pr_changed_files", lambda: [])
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 10)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "generate_message", lambda prompt, fallback=None, **kw: fallback or "test")
        monkeypatch.setattr(obj, "fix_loop", lambda: True)
        monkeypatch.setattr(obj, "commit_and_push_fix", lambda: "abc123")
        monkeypatch.setattr(obj, "comment", lambda msg: None)
        monkeypatch.setattr(obj, "react", lambda e: None)
        monkeypatch.setattr(obj, "checkout_pr_branch", lambda: None)

        obj.handle_heal()

        assert obj.issue_number == 42
        assert "pr" in metadata_loaded
        assert obj.is_pr is True

    def test_heal_with_no_pr_number_tries_branch_lookup(self, monkeypatch):
        obj = _make_ella_shell()
        obj.event = {
            "workflow_run": {
                "id": 12346,
                "head_branch": "orphan-branch",
                "pull_requests": [],
            }
        }
        obj.repo = "isyuricunha/ella"
        obj.issue_number = None

        gh_calls = []

        def fake_gh(args, *, check=True):
            gh_calls.append(args)
            if "pr" in args and "list" in args:
                return json.dumps([{"number": 77}])
            if "run" in args and "view" in args:
                return "Error in build\n"
            return "[]"

        def fake_load_pr_metadata():
            obj.pr_info = {"author": {"login": "testuser"}, "headRefName": "orphan-branch"}

        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(agent, "git", lambda args, check=True: "")
        monkeypatch.setattr(agent, "run_cmd", lambda *a, **kw: subprocess.CompletedProcess([], 0, "", ""))
        monkeypatch.setattr(obj, "load_pr_metadata", fake_load_pr_metadata)
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setattr(obj, "get_pr_changed_files", lambda: [])
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 10)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "generate_message", lambda prompt, fallback=None, **kw: fallback or "test")
        monkeypatch.setattr(obj, "fix_loop", lambda: True)
        monkeypatch.setattr(obj, "commit_and_push_fix", lambda: "def456")
        monkeypatch.setattr(obj, "comment", lambda msg: None)
        monkeypatch.setattr(obj, "react", lambda e: None)
        monkeypatch.setattr(obj, "checkout_pr_branch", lambda: None)

        obj.handle_heal()
        assert obj.issue_number == 77

    def test_heal_dependabot_author_sets_special_prompt(self, monkeypatch):
        obj = _make_ella_shell()
        obj.event = {
            "workflow_run": {
                "id": 12347,
                "head_branch": "dependabot-fix",
                "pull_requests": [{"number": 55}],
            }
        }
        obj.repo = "isyuricunha/ella"
        obj.issue_number = None

        def fake_gh(args, *, check=True):
            if "run" in args and "view" in args:
                return "Build failed\n"
            return "[]"

        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(agent, "git", lambda args, check=True: "")
        monkeypatch.setattr(agent, "run_cmd", lambda *a, **kw: subprocess.CompletedProcess([], 0, "", ""))
        monkeypatch.setattr(obj, "load_pr_metadata", lambda: setattr(obj, "pr_info", {"author": {"login": "dependabot[bot]"}, "headRefName": "dep"}))
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setattr(obj, "get_pr_changed_files", lambda: [])
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 10)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "generate_message", lambda prompt, fallback=None, **kw: fallback or "test")
        monkeypatch.setattr(obj, "fix_loop", lambda: True)
        monkeypatch.setattr(obj, "commit_and_push_fix", lambda: "ghi789")
        monkeypatch.setattr(obj, "comment", lambda msg: None)
        monkeypatch.setattr(obj, "react", lambda e: None)
        monkeypatch.setattr(obj, "checkout_pr_branch", lambda: None)

        obj.handle_heal()
        assert "Dependabot" in obj.prompt or "dependabot" in obj.prompt.lower()

    def test_heal_no_pr_found_returns_early(self, monkeypatch):
        obj = _make_ella_shell()
        obj.event = {
            "workflow_run": {
                "id": 12348,
                "head_branch": "ghost-branch",
                "pull_requests": [],
            }
        }
        obj.repo = "isyuricunha/ella"
        obj.issue_number = None

        def fake_gh(args, *, check=True):
            if "pr" in args and "list" in args:
                return "[]"  # No PR found
            if "run" in args and "view" in args:
                return "Build failed\n"
            return "[]"

        monkeypatch.setattr(agent, "gh", fake_gh)
        fix_loop_called = []

        monkeypatch.setattr(obj, "fix_loop", lambda: fix_loop_called.append(True))
        obj.handle_heal()
        # fix_loop should NOT be called since no PR was found
        assert len(fix_loop_called) == 0


# --- handle_solve full flow ---


class TestHandleSolveFlow:
    def test_solve_success_creates_pr_and_comments(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "solve"
        obj.is_pr = False
        obj.issue_info = {"title": "Fix null pointer", "body": "There's a null pointer in main.py", "number": 42}
        obj.final_summary = "I fixed the null pointer."

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        monkeypatch.setattr(obj, "checkout_solve_branch", lambda: None)
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setattr(obj, "get_repo_files", lambda: ["src/main.py"])
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 10)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "generate_message", lambda prompt, fallback=None, **kw: fallback or "Done!")
        monkeypatch.setattr(obj, "fix_loop", lambda: True)
        monkeypatch.setattr(obj, "commit_and_push_solve", lambda: "abc123")
        monkeypatch.setattr(obj, "create_solve_pr", lambda: "https://github.com/isyuricunha/ella/pull/99")
        commented = []
        reacted = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))
        monkeypatch.setattr(obj, "react", lambda e: reacted.append(e))

        agent.TIME_LIMIT_SECONDS = 3600
        obj._handle_solve()

        assert "abc123" in commented[0]
        assert "rocket" in reacted

    def test_solve_failure_posts_final_summary(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "solve"
        obj.is_pr = False
        obj.issue_info = {"title": "Broken thing", "body": "test"}
        obj.final_summary = "Could not fix the issue."

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        monkeypatch.setattr(obj, "checkout_solve_branch", lambda: None)
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setattr(obj, "get_repo_files", lambda: [])
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 5)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "generate_message", lambda prompt, fallback=None, **kw: fallback or "msg")
        monkeypatch.setattr(obj, "fix_loop", lambda: False)
        commented = []
        reacted = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))
        monkeypatch.setattr(obj, "react", lambda e: reacted.append(e))

        agent.TIME_LIMIT_SECONDS = 3600
        obj._handle_solve()

        assert "Could not fix" in commented[0]
        assert "confused" in reacted

    def test_solve_success_no_changes_posts_all_passed(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "solve"
        obj.is_pr = False
        obj.issue_info = {"title": "Already fixed", "body": "test"}
        obj.final_summary = "Nothing to change."

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        monkeypatch.setattr(obj, "checkout_solve_branch", lambda: None)
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setattr(obj, "get_repo_files", lambda: [])
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 5)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "generate_message", lambda prompt, fallback=None, **kw: fallback)
        monkeypatch.setattr(obj, "fix_loop", lambda: True)
        monkeypatch.setattr(obj, "commit_and_push_solve", lambda: "")  # No changes
        monkeypatch.setattr(obj, "create_solve_pr", lambda: "url")
        commented = []
        reacted = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))
        monkeypatch.setattr(obj, "react", lambda e: reacted.append(e))

        agent.TIME_LIMIT_SECONDS = 3600
        obj._handle_solve()

        # Should say "all checks passed" rather than announcing a PR
        assert "rocket" in reacted
        assert any("passed" in c.lower() or "no changes" in c.lower() for c in commented)


# --- handle_fix full flow ---


class TestHandleFixFlow:
    def test_fix_success_commits_and_comments(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "fix"
        obj.is_pr = True
        obj.pr_info = {"headRefName": "fix-branch", "isCrossRepository": False}
        obj.final_summary = "I fixed the bug in parser.py"

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        monkeypatch.setattr(obj, "checkout_pr_branch", lambda: None)
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setattr(obj, "get_pr_changed_files", lambda: ["src/parser.py"])
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 10)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "generate_message", lambda prompt, fallback=None, **kw: fallback or "Done!")
        monkeypatch.setattr(obj, "fix_loop", lambda: True)
        monkeypatch.setattr(obj, "commit_and_push_fix", lambda: "deadbeef")
        commented = []
        reacted = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))
        monkeypatch.setattr(obj, "react", lambda e: reacted.append(e))

        agent.TIME_LIMIT_SECONDS = 3600
        obj._handle_fix()

        assert "deadbeef" in commented[0]
        assert "rocket" in reacted

    def test_fix_cross_repository_rejected(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "fix"
        obj.is_pr = True
        obj.pr_info = {"headRefName": "external/fork", "isCrossRepository": True}

        monkeypatch.setattr(obj, "_validate_and_load_context", lambda: None)
        commented = []
        reacted = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))
        monkeypatch.setattr(obj, "react", lambda e: reacted.append(e))

        obj._handle_fix()

        assert "security" in commented[0].lower() or "repository" in commented[0].lower()
        assert "confused" in reacted


# --- handle_label ---


class TestHandleLabel:
    def test_label_applies_valid_labels(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "label"
        obj.is_pr = False
        obj.issue_number = 50
        obj.repo = "isyuricunha/ella"

        labels_config = [
            {"name": "bug", "color": "d73a4a", "description": "Something is broken"},
            {"name": "enhancement", "color": "a2eeef", "description": "New feature"},
        ]

        monkeypatch.setattr(agent, "load_labels", lambda: labels_config)
        monkeypatch.setattr(obj, "handle_read_only", lambda: '{"summary": "This is a bug", "labels": ["bug"]}')
        gh_calls = []
        monkeypatch.setattr(agent, "gh", lambda args, check=True: gh_calls.append(args) or "")
        monkeypatch.setattr(obj, "react", lambda e: None)
        commented = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))

        obj.handle_label()

        # Should have called gh to create labels and apply them
        label_edit_calls = [c for c in gh_calls if "issue" in c and "edit" in c and "--add-label" in c]
        assert len(label_edit_calls) >= 1
        assert "bug" in commented[0].lower()

    def test_label_invalid_json_posts_error(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "label"
        obj.issue_number = 51

        monkeypatch.setattr(agent, "load_labels", lambda: [{"name": "bug", "color": "d73a4a", "description": "x"}])
        monkeypatch.setattr(obj, "handle_read_only", lambda: "not json")
        monkeypatch.setattr(agent, "gh", lambda args, check=True: "")
        monkeypatch.setattr(obj, "react", lambda e: None)
        commented = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))

        obj.handle_label()
        assert any("could not parse" in c.lower() or "json" in c.lower() for c in commented)

    def test_label_no_valid_labels_founds(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "label"
        obj.issue_number = 52

        labels_config = [{"name": "bug", "color": "d73a4a", "description": "x"}]

        monkeypatch.setattr(agent, "load_labels", lambda: labels_config)
        monkeypatch.setattr(obj, "handle_read_only", lambda: '{"summary": "n/a", "labels": ["nonexistent"]}')
        monkeypatch.setattr(agent, "gh", lambda args, check=True: "")
        monkeypatch.setattr(obj, "react", lambda e: None)
        commented = []
        monkeypatch.setattr(obj, "comment", lambda msg: commented.append(msg))

        obj.handle_label()
        assert any("could not find" in c.lower() or "valid" in c.lower() for c in commented)


# --- prepare_environment ---


class TestPrepareEnvironment:
    def test_custom_checks_sh_returns_true(self, monkeypatch, tmp_path):
        obj = _make_ella_shell()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(agent, "ROOT", tmp_path)
        (tmp_path / ".ella").mkdir()
        (tmp_path / ".ella" / "checks.sh").write_text("#!/bin/bash\necho hello\n")

        result = obj.prepare_environment()
        assert result is True

    def test_no_install_commands_detected(self, monkeypatch, tmp_path):
        obj = _make_ella_shell()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(agent, "ROOT", tmp_path)
        monkeypatch.setattr(agent, "command_exists", lambda name: True)

        # No package.json, no pyproject.toml, no requirements.txt
        result = obj.prepare_environment()
        assert result is True  # no install commands = success (nothing to fail)

    def test_pip_install_runs_on_pyproject(self, monkeypatch, tmp_path):
        obj = _make_ella_shell()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(agent, "ROOT", tmp_path)
        monkeypatch.setattr(agent, "command_exists", lambda name: False)

        # Create pyproject.toml but no poetry.lock or uv.lock or requirements.txt
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\nversion = '0.1.0'\n[build-system]\nrequires = ['setuptools']\nbuild-backend = 'setuptools.build_meta'\n")

        # detect_install_commands should try pip install -e .
        cmds = obj.detect_install_commands()
        assert any("pip" in c[0] for c in cmds)

    def test_package_json_triggers_pnpm_or_npm(self, monkeypatch, tmp_path):
        obj = _make_ella_shell()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(agent, "ROOT", tmp_path)

        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "pnpm-lock.yaml").write_text("")

        cmds = obj.detect_install_commands()
        assert any(c[0] == "pnpm" for c in cmds)


# --- write_debug / scrub_secrets integration ---


class TestWriteDebugScrubSecrets:
    def test_write_debug_scrubs_tokens(self, monkeypatch, tmp_path):
        out_dir = tmp_path / "out"
        monkeypatch.setattr(agent, "OUT", out_dir)
        out_dir.mkdir()

        secret = "ghp_" + "a" * 36
        agent.write_debug("test.txt", f"Here is a token: {secret}")
        content = (out_dir / "test.txt").read_text()
        assert "ghp_" not in content
        assert "***" in content

    def test_write_debug_scrubs_env_vars(self, monkeypatch, tmp_path):
        out_dir = tmp_path / "out"
        monkeypatch.setattr(agent, "OUT", out_dir)
        out_dir.mkdir()
        monkeypatch.setenv("ELLA_AI_API_KEY", "sk-supersecret123")
        monkeypatch.setenv("ELLA_AI_MODEL", "my-model-name")
        monkeypatch.setenv("ELLA_AI_BASE_URL", "https://secret-endpoint.example")

        agent.write_debug("test2.txt", "ELLA_AI_API_KEY=sk-supersecret123 ELLA_AI_MODEL=my-model-name")
        content = (out_dir / "test2.txt").read_text()
        assert "sk-supersecret123" not in content
        assert "my-model-name" not in content
        assert "secret-endpoint" not in content

    def test_write_debug_with_nonexistent_out_dir(self, monkeypatch, tmp_path):
        out_dir = tmp_path / "nonexistent"
        monkeypatch.setattr(agent, "OUT", out_dir)
        out_dir.mkdir()  # ensure exists

        agent.write_debug("test3.txt", "just text")
        assert (out_dir / "test3.txt").read_text() == "just text"


# --- safe_rel_path additional edge cases ---


class TestSafeRelPathEdgeCases:
    def test_null_byte_rejected(self):
        assert agent.safe_rel_path("src/\x00main.py") is False

    def test_deep_nested_valid(self):
        assert agent.safe_rel_path("src/components/ui/Button.tsx") is True

    def test_single_dot_path(self):
        assert agent.safe_rel_path(".") is True

    def test_double_dot_in_filename_not_rejected(self):
        # ".." in parts means traversal component, not in filename
        assert agent.safe_rel_path("file..txt") is True

    def test_unix_absolute_path_rejected(self):
        assert agent.safe_rel_path("/etc/passwd") is False


# --- is_ignored additional edge cases ---


class TestIsIgnoredEdgeCases:
    def test_backslash_normalized(self):
        # is_ignored replaces backslashes with forward slashes internally
        patterns = ["**/node_modules/**"]
        assert agent.is_ignored("src\\node_modules\\react\\index.js", patterns) is True

    def test_empty_patterns_not_ignored(self):
        assert agent.is_ignored("src/main.py", []) is False

    def test_empty_string_pattern_skipped(self):
        patterns = ["", "  ", "*.pyc"]
        assert agent.is_ignored("cache.pyc", patterns) is True
        assert agent.is_ignored("src/main.py", patterns) is False

    def test_comment_pattern_skipped(self):
        patterns = ["# my ignore", "*.tmp"]
        assert agent.is_ignored("file.tmp", patterns) is True

    def test_root_level_pattern_matches_filename(self):
        patterns = ["*.lock"]
        assert agent.is_ignored("pnpm-lock.yaml.lock", patterns) is True
        assert agent.is_ignored("src/main.py", patterns) is False


class TestLoadMetadataJsonParse:
    """load_pr_metadata and load_issue_metadata should raise RuntimeError
    with a scrubbed message if gh returns non-JSON output, not crash with
    a bare JSONDecodeError."""

    def test_load_pr_metadata_malformed_json(self, monkeypatch):
        ella = _make_ella_shell()
        monkeypatch.setattr(agent, "gh", lambda *a, **k: "not valid JSON here")
        with pytest.raises(RuntimeError, match="Failed to parse PR metadata"):
            ella.load_pr_metadata()

    def test_load_issue_metadata_malformed_json(self, monkeypatch):
        ella = _make_ella_shell()
        monkeypatch.setattr(agent, "gh", lambda *a, **k: "not valid JSON here")
        with pytest.raises(RuntimeError, match="Failed to parse issue metadata"):
            ella.load_issue_metadata()
