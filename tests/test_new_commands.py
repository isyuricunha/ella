"""Tests for the 5 new features: /ella close, reopen, assign, milestone,
and PR review request routing (pull_request_review -> review_fix)."""

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

AGENT_PATH = Path(__file__).resolve().parent.parent / ".ella" / "agent.py"


def _load_agent_module():
    spec = importlib.util.spec_from_file_location("ella_agent", AGENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = _load_agent_module()


def _make_shell():
    """Create an Ella instance without calling __init__."""
    obj = object.__new__(agent.Ella)
    obj.mode = "close"
    obj.prompt = ""
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


def _patch_gh(handler_fn, side_effects=None):
    """Decorator/context to properly mock gh for handler tests.

    side_effects: if provided, return a MagicMock with side_effect.
    """
    if side_effects is not None:
        return patch.object(agent, "gh", side_effect=side_effects)
    return patch.object(agent, "gh")


# --- /ella close ---


class TestHandleClose:
    def test_close_with_valid_reason_completed(self):
        obj = _make_shell()
        obj.prompt = "completed"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment") as mock_comment:
            agent.Ella._handle_close(obj)
            mock_gh.assert_called_once()
            args = mock_gh.call_args[0][0]
            assert "state=closed" in args
            assert "state_reason=completed" in args
            # 'completed' is a valid reason so no comment text
            mock_comment.assert_not_called()

    def test_close_with_valid_reason_not_planned(self):
        obj = _make_shell()
        obj.prompt = "not_planned"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_close(obj)
            args = mock_gh.call_args[0][0]
            assert "state_reason=not_planned" in args

    def test_close_with_valid_reason_duplicate(self):
        obj = _make_shell()
        obj.prompt = "duplicate"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_close(obj)
            args = mock_gh.call_args[0][0]
            assert "state_reason=duplicate" in args

    def test_close_with_unknown_text_defaults_to_not_planned(self):
        obj = _make_shell()
        obj.prompt = "this is broken"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment"), \
             patch.object(agent.Ella, "generate_message", return_value="closed"):
            agent.Ella._handle_close(obj)
            args = mock_gh.call_args[0][0]
            assert "state_reason=not_planned" in args

    def test_close_without_reason_defaults_to_not_planned(self):
        obj = _make_shell()
        obj.prompt = ""
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_close(obj)
            args = mock_gh.call_args[0][0]
            assert "state_reason=not_planned" in args

    def test_close_with_free_text_posts_comment(self):
        obj = _make_shell()
        obj.prompt = "this is broken"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "generate_message", return_value="closed"):
            agent.Ella._handle_close(obj)
            assert mock_comment.called

    def test_close_with_invalid_issue_number(self):
        obj = _make_shell()
        obj.issue_number = -1
        obj.prompt = ""
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_close(obj)
            mock_gh.assert_not_called()
            mock_comment.assert_called_once()

    def test_close_gh_failure_does_not_silently_succeed(self):
        obj = _make_shell()
        obj.prompt = ""
        with patch.object(agent, "gh", side_effect=Exception("API error")), \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_close(obj)
            mock_comment.assert_called_once()
            assert "Failed" in mock_comment.call_args[0][0]


# --- /ella reopen ---


class TestHandleReopen:
    def test_reopen_calls_api_with_state_open(self):
        obj = _make_shell()
        obj.prompt = ""
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_reopen(obj)
            args = mock_gh.call_args[0][0]
            assert "state=open" in args
            assert "PATCH" in args

    def test_reopen_with_comment(self):
        obj = _make_shell()
        obj.prompt = "Need more info"
        with patch.object(agent, "gh"), \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "generate_message") as mock_gen:
            mock_gen.return_value = "Reopened!"
            agent.Ella._handle_reopen(obj)
            mock_gen.assert_called_once()
            assert "Need more info" in mock_gen.call_args[0][0]

    def test_reopen_invalid_issue_number(self):
        obj = _make_shell()
        obj.issue_number = -1
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_reopen(obj)
            mock_gh.assert_not_called()
            mock_comment.assert_called_once()

    def test_reopen_gh_failure_does_not_silently_succeed(self):
        obj = _make_shell()
        obj.prompt = ""
        with patch.object(agent, "gh", side_effect=Exception("API error")), \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_reopen(obj)
            mock_comment.assert_called_once()
            assert "Failed" in mock_comment.call_args[0][0]


# --- /ella assign ---


class TestHandleAssign:
    def test_assign_at_prefix_stripped(self):
        obj = _make_shell()
        obj.prompt = "@yuri"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment"):
            agent.Ella._handle_assign(obj)
            args = mock_gh.call_args[0][0]
            assert "yuri" in args

    def test_assign_without_at_prefix(self):
        obj = _make_shell()
        obj.prompt = "yuri"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment"):
            agent.Ella._handle_assign(obj)
            args = mock_gh.call_args[0][0]
            assert "yuri" in args

    def test_assign_empty_user_errors(self):
        obj = _make_shell()
        obj.prompt = ""
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_assign(obj)
            mock_gh.assert_not_called()
            mock_comment.assert_called_once()

    def test_assign_invalid_issue_number(self):
        obj = _make_shell()
        obj.issue_number = -1
        obj.prompt = "@yuri"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_assign(obj)
            mock_gh.assert_not_called()
            mock_comment.assert_called_once()

    def test_assign_user_not_found(self):
        obj = _make_shell()
        obj.prompt = "@ghost"
        with patch.object(agent, "gh", side_effect=Exception("user not found")), \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_assign(obj)
            mock_comment.assert_called_once()
            assert "doesn't exist" in mock_comment.call_args[0][0]


# --- /ella milestone ---


class TestHandleMilestone:
    def test_milestone_finds_existing_by_name(self):
        obj = _make_shell()
        obj.prompt = "v2.0"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment"):
            mock_gh.side_effect = [
                json.dumps([{"number": 5, "title": "v2.0"}, {"number": 6, "title": "v3.0"}]),
                "",
            ]
            agent.Ella._handle_milestone(obj)
            second_call_args = mock_gh.call_args_list[1][0][0]
            assert "v2.0" in second_call_args

    def test_milestone_case_insensitive(self):
        obj = _make_shell()
        obj.prompt = "V2.0"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment"):
            mock_gh.side_effect = [
                json.dumps([{"number": 5, "title": "v2.0"}]),
                "",
            ]
            agent.Ella._handle_milestone(obj)
            # Should pass the actual title (lowercase from the API) to gh
            second_call_args = mock_gh.call_args_list[1][0][0]
            assert "v2.0" in second_call_args

    def test_milestone_strips_quotes(self):
        obj = _make_shell()
        obj.prompt = '"v2.0"'
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "react"), \
             patch.object(agent.Ella, "comment"):
            mock_gh.side_effect = [
                json.dumps([{"number": 5, "title": "v2.0"}]),
                "",
            ]
            agent.Ella._handle_milestone(obj)
            second_call_args = mock_gh.call_args_list[1][0][0]
            assert "v2.0" in second_call_args

    def test_milestone_not_found_lists_available(self):
        obj = _make_shell()
        obj.prompt = "v9.0"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            mock_gh.side_effect = [
                json.dumps([{"number": 5, "title": "v2.0"}, {"number": 6, "title": "v3.0"}]),
            ]
            agent.Ella._handle_milestone(obj)
            mock_comment.assert_called_once()
            assert "v2.0" in mock_comment.call_args[0][0]
            assert "v3.0" in mock_comment.call_args[0][0]

    def test_milestone_empty_title_errors(self):
        obj = _make_shell()
        obj.prompt = ""
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_milestone(obj)
            mock_gh.assert_not_called()
            mock_comment.assert_called_once()

    def test_milestone_invalid_issue_number(self):
        obj = _make_shell()
        obj.issue_number = -1
        obj.prompt = "v2.0"
        with patch.object(agent, "gh") as mock_gh, \
             patch.object(agent.Ella, "comment") as mock_comment, \
             patch.object(agent.Ella, "react"):
            agent.Ella._handle_milestone(obj)
            mock_gh.assert_not_called()
            mock_comment.assert_called_once()


# --- PR review request routing ---


class TestPullRequestReviewRouting:
    def test_changes_requested_routes_to_review_fix(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "action": "submitted",
            "pull_request": {"number": 25},
            "review": {"state": "changes_requested", "body": "Fix the typo"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_review")
        obj = agent.Ella()
        obj.parse_command()
        assert obj.mode == "review_fix"
        assert "changes requested" in obj.prompt.lower() or "review feedback" in obj.prompt.lower()

    def test_approved_review_does_not_route_to_fix(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "action": "submitted",
            "pull_request": {"number": 25},
            "review": {"state": "approved", "body": "Looks good!"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_review")
        obj = agent.Ella()
        obj.parse_command()
        assert obj.mode != "review_fix"

    def test_commented_review_does_not_route_to_fix(self, monkeypatch, tmp_path):
        event = {
            "repository": {"default_branch": "main"},
            "action": "submitted",
            "pull_request": {"number": 25},
            "review": {"state": "commented", "body": "Nice code"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_review")
        obj = agent.Ella()
        obj.parse_command()
        assert obj.mode != "review_fix"

    def test_review_fix_dispatches_to_handle_fix(self):
        assert agent.Ella._dispatch["review_fix"] == agent.Ella._dispatch["fix"]

    def test_review_fix_in_pr_only_set(self):
        """review_fix should be in pr_only so it can't run on issues."""
        obj = _make_shell()
        obj.mode = "review_fix"
        obj.is_pr = False
        with patch.object(agent.Ella, "validate_ai_config"), \
             patch.object(agent.Ella, "comment"), \
             patch.object(agent.Ella, "react"):
            error = obj._validate_and_load_context()
            assert error == "That command needs to be used inside a PR."


# --- parse_command for new slash commands ---


def _parse_command_for_comment(monkeypatch, tmp_path, body):
    event = {
        "repository": {"default_branch": "main"},
        "issue": {"number": 30},
        "comment": {"body": body, "user": {"login": "isyuricunha"}, "id": 999},
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "isyuricunha/ella")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "issue_comment")
    obj = agent.Ella()
    obj.parse_command()
    return obj


class TestParseNewCommands:
    def test_close_command_parsed(self, monkeypatch, tmp_path):
        obj = _parse_command_for_comment(monkeypatch, tmp_path, "/ella close")
        assert obj.mode == "close"
        assert obj.prompt == ""

    def test_close_with_reason_parsed(self, monkeypatch, tmp_path):
        obj = _parse_command_for_comment(monkeypatch, tmp_path, "/ella close not_planned")
        assert obj.mode == "close"
        assert "not_planned" in obj.prompt

    def test_reopen_command_parsed(self, monkeypatch, tmp_path):
        obj = _parse_command_for_comment(monkeypatch, tmp_path, "/ella reopen")
        assert obj.mode == "reopen"

    def test_reopen_with_comment_parsed(self, monkeypatch, tmp_path):
        obj = _parse_command_for_comment(monkeypatch, tmp_path, "/ella reopen this is still broken")
        assert obj.mode == "reopen"
        assert "still broken" in obj.prompt

    def test_assign_command_parsed(self, monkeypatch, tmp_path):
        obj = _parse_command_for_comment(monkeypatch, tmp_path, "/ella assign @yuri")
        assert obj.mode == "assign"
        assert "@yuri" in obj.prompt

    def test_milestone_command_parsed(self, monkeypatch, tmp_path):
        obj = _parse_command_for_comment(monkeypatch, tmp_path, '/ella milestone "v2.0"')
        assert obj.mode == "milestone"
        assert "v2.0" in obj.prompt


# --- dispatch table coverage ---


class TestDispatchTable:
    def test_all_new_modes_in_dispatch(self):
        for mode in ["close", "reopen", "assign", "milestone", "review_fix"]:
            assert mode in agent.Ella._dispatch, f"{mode} missing from _dispatch"

    def test_review_fix_uses_fix_handler(self):
        assert agent.Ella._dispatch["review_fix"] is agent.Ella._handle_fix


# --- help_text coverage ---


class TestHelpText:
    def test_help_text_includes_new_commands(self):
        text = agent.Ella.help_text(_make_shell())
        for cmd in ["/ella close", "/ella reopen", "/ella assign", "/ella milestone"]:
            assert cmd in text, f"{cmd} missing from help_text"

    def test_help_text_mentions_auto_review_fix(self):
        text = agent.Ella.help_text(_make_shell())
        assert "reviewer requests changes" in text.lower()


# --- _validate_and_load_context ---


class TestValidateNewModes:
    def test_close_works_on_pr(self):
        obj = _make_shell()
        obj.mode = "close"
        obj.is_pr = True
        with patch.object(agent.Ella, "validate_ai_config"), \
             patch.object(agent.Ella, "load_pr_metadata"):
            error = obj._validate_and_load_context()
            assert error is None or error == "__skip__"

    def test_assign_works_on_issue(self):
        obj = _make_shell()
        obj.mode = "assign"
        obj.is_pr = False
        with patch.object(agent.Ella, "validate_ai_config"), \
             patch.object(agent.Ella, "load_issue_metadata"):
            error = obj._validate_and_load_context()
            assert error is None or error == "__skip__"
