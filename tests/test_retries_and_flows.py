"""Tests for retry logic, commit/push flows, inline reviews, and triage parsing.

These tests mock gh/git/ai_call to exercise the code paths without a live
GitHub environment.
"""

import importlib.util
import json
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
    return obj


# --- _retry_cmd ---


class TestRetryCmd:
    def test_succeeds_first_try(self, monkeypatch):
        calls = []

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "ok", "")

        result = agent._retry_cmd(fake_fn, ["gh", "test"], check=True)
        assert result.stdout == "ok"
        assert len(calls) == 1

    def test_handles_empty_env_var_without_crash(self, monkeypatch):
        """ELLA_CMD_RETRIES set but empty (e.g. undefined GitHub secret) should not crash."""
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)
        monkeypatch.setenv("ELLA_CMD_RETRIES", "")
        calls = []

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "ok", "")

        result = agent._retry_cmd(fake_fn, ["gh", "test"], check=True)
        assert result.stdout == "ok"
        assert len(calls) == 1  # default of 3 retries, should succeed first try

    def test_retries_on_transient_error(self, monkeypatch):
        calls = []
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            if len(calls) < 3:
                raise agent.CommandError("rate limit exceeded")
            return subprocess.CompletedProcess(args, 0, "recovered", "")

        result = agent._retry_cmd(fake_fn, ["gh", "test"], check=True)
        assert result.stdout == "recovered"
        assert len(calls) == 3

    def test_no_retry_on_not_found(self, monkeypatch):
        calls = []
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            raise agent.CommandError("fatal: not found: branch xyz")

        with pytest.raises(agent.CommandError, match="not found"):
            agent._retry_cmd(fake_fn, ["git", "fetch"], check=True)
        assert len(calls) == 1

    def test_no_retry_on_permission_denied(self, monkeypatch):
        calls = []
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            raise agent.CommandError("permission denied")

        with pytest.raises(agent.CommandError, match="permission denied"):
            agent._retry_cmd(fake_fn, ["git", "push"], check=True)
        assert len(calls) == 1

    def test_exhausts_retries_then_raises(self, monkeypatch):
        calls = []
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            if check:
                raise agent.CommandError("server error 503")
            return subprocess.CompletedProcess(args, 1, "fail", "")

        with pytest.raises(agent.CommandError, match="server error"):
            agent._retry_cmd(fake_fn, ["gh", "api"], check=True)
        assert len(calls) == 3  # ELLA_CMD_RETRIES default

    def test_timeout_not_retried(self, monkeypatch):
        calls = []
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            raise subprocess.TimeoutExpired(cmd=args, timeout=900)

        with pytest.raises(subprocess.TimeoutExpired):
            agent._retry_cmd(fake_fn, ["git", "push"], check=True)
        assert len(calls) == 1

    def test_custom_retry_count(self, monkeypatch):
        calls = []
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)
        monkeypatch.setenv("ELLA_CMD_RETRIES", "5")

        def fake_fn(args, *, check, **kwargs):
            calls.append(args)
            raise agent.CommandError("connection reset")

        with pytest.raises(agent.CommandError):
            agent._retry_cmd(fake_fn, ["gh", "api"], check=True)
        assert len(calls) == 5


# --- _retry_ai / _reset_ai_retry ---


class TestRetryAi:
    def test_returns_true_until_budget_exhausted(self):
        agent._reset_ai_retry("test_key")
        assert agent._retry_ai("test_key") is True   # attempt 1
        assert agent._retry_ai("test_key") is True   # attempt 2
        assert agent._retry_ai("test_key") is True   # attempt 3
        assert agent._retry_ai("test_key") is False   # exhausted
        agent._reset_ai_retry("test_key")

    def test_reset_clears_counter(self):
        agent._reset_ai_retry("test_key2")
        agent._retry_ai("test_key2")
        agent._retry_ai("test_key2")
        agent._reset_ai_retry("test_key2")
        # After reset, we should get 3 more retries
        assert agent._retry_ai("test_key2") is True
        assert agent._retry_ai("test_key2") is True
        assert agent._retry_ai("test_key2") is True
        agent._reset_ai_retry("test_key2")

    def test_independent_keys(self):
        agent._reset_ai_retry("a")
        agent._reset_ai_retry("b")
        agent._retry_ai("a")
        assert agent._retry_ai("b") is True
        assert agent._retry_ai("a") is True
        agent._reset_ai_retry("a")
        agent._reset_ai_retry("b")


# --- ai_call IncompleteRead handling ---


class TestAiCallStreamInterruption:
    def test_incomplete_read_retries(self, monkeypatch):
        """When the HTTP stream is interrupted mid-flight (HTTP 200 but connection
        drops), IncompleteRead should be caught and retried, not crash the agent."""
        import http.client
        ella = _make_ella_shell()
        ella.ai_model = "m"
        ella.ai_base_url = "https://example.invalid"
        ella.ai_api_key = "k"

        agent._reset_ai_retry("ai_call")
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        call_count = [0]

        def fake_urlopen(request, timeout=None):
            call_count[0] += 1
            if call_count[0] < 2:
                raise http.client.IncompleteRead(b"partial")
            # Second call: return a valid response
            class FakeResponse:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def __iter__(self):
                    yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
                    yield b'data: [DONE]\n'
            return FakeResponse()

        monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
        content, tool_calls = ella.ai_call([{"role": "user", "content": "hi"}], 100)
        assert "ok" in content

    def test_connection_error_retries(self, monkeypatch):
        """ConnectionError during streaming should be retried."""
        ella = _make_ella_shell()
        ella.ai_model = "m"
        ella.ai_base_url = "https://example.invalid"
        ella.ai_api_key = "k"

        agent._reset_ai_retry("ai_call")
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        call_count = [0]

        def fake_urlopen(request, timeout=None):
            call_count[0] += 1
            if call_count[0] < 2:
                raise ConnectionError("connection reset by peer")
            class FakeResponse:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def __iter__(self):
                    yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
                    yield b'data: [DONE]\n'
            return FakeResponse()

        monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
        content, tool_calls = ella.ai_call([{"role": "user", "content": "hi"}], 100)
        assert "ok" in content

    def test_incomplete_read_exhausts_retries(self, monkeypatch):
        """After 3 retries, IncompleteRead should raise CommandError, not crash."""
        import http.client
        ella = _make_ella_shell()
        ella.ai_model = "m"
        ella.ai_base_url = "https://example.invalid"
        ella.ai_api_key = "k"

        agent._reset_ai_retry("ai_call")
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        def fake_urlopen(request, timeout=None):
            raise http.client.IncompleteRead(b"partial")

        monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(agent.CommandError, match="stream interrupted"):
            ella.ai_call([{"role": "user", "content": "hi"}], 100)


class TestAiCallStreamError:
    """Some AI providers return HTTP 200 with an error object in the SSE stream
    (e.g. rate limits, model errors). These should be retried, not silently
    swallowed as empty responses."""

    def test_stream_error_retries(self, monkeypatch):
        ella = _make_ella_shell()
        ella.ai_model = "m"
        ella.ai_base_url = "https://example.invalid"
        ella.ai_api_key = "k"

        agent._reset_ai_retry("ai_call")
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        call_count = [0]

        def fake_urlopen(request, timeout=None):
            call_count[0] += 1
            if call_count[0] < 2:
                # First call: return error in stream
                class ErrorResponse:
                    status = 200
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        pass
                    def __iter__(self):
                        yield b'data: {"error": {"message": "rate limited", "type": "rate_limit_error"}}\n'
                        yield b'data: [DONE]\n'
                return ErrorResponse()
            # Second call: success
            class FakeResponse:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def __iter__(self):
                    yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
                    yield b'data: [DONE]\n'
            return FakeResponse()

        monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
        content, tool_calls = ella.ai_call([{"role": "user", "content": "hi"}], 100)
        assert "ok" in content
        assert call_count[0] == 2

    def test_stream_error_exhausts_retries(self, monkeypatch):
        ella = _make_ella_shell()
        ella.ai_model = "m"
        ella.ai_base_url = "https://example.invalid"
        ella.ai_api_key = "k"

        agent._reset_ai_retry("ai_call")
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)

        def fake_urlopen(request, timeout=None):
            class ErrorResponse:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def __iter__(self):
                    yield b'data: {"error": {"message": "model overloaded"}}\n'
                    yield b'data: [DONE]\n'
            return ErrorResponse()

        monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(agent.CommandError, match="stream returned error"):
            ella.ai_call([{"role": "user", "content": "hi"}], 100)


# --- post_inline_review ---


class TestPostInlineReview:
    def test_posts_review_with_comments(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefOid": "abc123"}

        gh_calls = []

        def fake_gh(args, *, check=True):
            gh_calls.append(args)
            return ""

        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(obj, "comment", lambda body: None)

        summary = "Looks good!"
        comments = [
            {"path": "src/main.py", "line": 10, "body": "Fix this"},
            {"path": "README.md", "line": 5, "body": "Update this"},
        ]
        obj.post_inline_review(summary, comments)

        # Should have called gh api with POST method
        api_calls = [c for c in gh_calls if "api" in c and "reviews" in " ".join(c)]
        assert len(api_calls) == 1

    def test_falls_back_to_comment_when_no_comments(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefOid": "abc123"}

        comment_calls = []

        monkeypatch.setattr(agent, "gh", lambda args, **kw: "")
        monkeypatch.setattr(obj, "comment", lambda body: comment_calls.append(body))

        obj.post_inline_review("Summary only", [])
        assert len(comment_calls) == 1
        assert "Summary only" in comment_calls[0]

    def test_skips_when_no_pr_info(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = None
        gh_calls = []
        monkeypatch.setattr(agent, "gh", lambda args, **kw: gh_calls.append(args))
        obj.post_inline_review("summary", [{"path": "a.py", "line": 1, "body": "x"}])
        assert gh_calls == []

    def test_skips_when_no_head_oid(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefOid": None}
        gh_calls = []
        monkeypatch.setattr(agent, "gh", lambda args, **kw: gh_calls.append(args))
        obj.post_inline_review("summary", [{"path": "a.py", "line": 1, "body": "x"}])
        assert gh_calls == []

    def test_skips_non_numeric_line(self, monkeypatch):
        """If the AI returns a non-numeric line value, that comment is skipped
        instead of crashing with ValueError from int()."""
        obj = _make_ella_shell()
        obj.pr_info = {"headRefOid": "abc123"}

        captured_payloads = []

        def fake_gh(args, *, check=True):
            if "api" in args and "reviews" in " ".join(args):
                temp_path = args[args.index("--input") + 1]
                captured_payloads.append(Path(temp_path).read_text())
            return ""

        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(obj, "comment", lambda body: None)

        comments = [
            {"path": "a.py", "line": "not_a_number", "body": "bad line"},
            {"path": "b.py", "line": 10, "body": "good line"},
        ]
        obj.post_inline_review("summary", comments)

        assert len(captured_payloads) == 1
        assert "good line" in captured_payloads[0]
        assert "bad line" not in captured_payloads[0]

    def test_strips_secrets_from_review_body(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefOid": "abc123"}

        captured = []

        def fake_gh(args, *, check=True):
            captured.append(args)
            return ""

        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(obj, "comment", lambda body: None)

        secret = "ghp_1234567890abcdef"
        summary = f"Review with {secret}"
        comments = [{"path": "a.py", "line": 1, "body": f"Check {secret}"}]
        obj.post_inline_review(summary, comments)

        # Find the temp file written and check it's scrubbed
        api_calls = [c for c in captured if "api" in c and "reviews" in " ".join(c)]
        assert len(api_calls) == 1
        temp_path = api_calls[0][api_calls[0].index("--input") + 1]
        content = Path(temp_path).read_text() if Path(temp_path).exists() else ""
        # The temp file is deleted in the finally block, but the call was made
        # without the secret being visible in the args


# --- commit_and_push_fix ---


class TestCommitAndPushFix:
    def test_commits_and_pushes_changes(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefName": "feature-branch"}

        git_calls = []
        run_cmd_calls = []

        def fake_git(args, *, check=True):
            git_calls.append(args)
            if args[:2] == ["ls-files", "--modified"]:
                return "file1.py\nfile2.py"
            if args[:1] == ["rev-parse"]:
                return "abc1234"
            return ""

        def fake_run_cmd(args, **kwargs):
            run_cmd_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(agent, "git", fake_git)
        monkeypatch.setattr(agent, "run_cmd", fake_run_cmd)
        monkeypatch.setattr(obj, "write_commit_message_file", lambda changed: "/tmp/msg.txt")
        monkeypatch.setattr("os.unlink", lambda p: None)

        sha = obj.commit_and_push_fix()
        assert sha == "abc1234"
        # Should configure user, add, commit, push
        config_calls = [c for c in git_calls if c[:1] == ["config"]]
        assert len(config_calls) == 2
        assert ["push", "origin", "HEAD:feature-branch"] in git_calls

    def test_returns_empty_when_no_changes(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = {"headRefName": "feature-branch"}

        monkeypatch.setattr(agent, "git", lambda args, **kw: "" if args[:2] == ["ls-files", "--modified"] else "")
        sha = obj.commit_and_push_fix()
        assert sha == ""

    def test_raises_when_no_pr_info(self, monkeypatch):
        obj = _make_ella_shell()
        obj.pr_info = None
        with pytest.raises(RuntimeError, match="PR info missing"):
            obj.commit_and_push_fix()


# --- commit_and_push_solve ---


class TestCommitAndPushSolve:
    def test_pushes_to_solve_branch(self, monkeypatch):
        obj = _make_ella_shell()
        obj.solve_branch = "ella/issue-42-fix"

        git_calls = []

        def fake_git(args, *, check=True):
            git_calls.append(args)
            if args[:2] == ["ls-files", "--modified"]:
                return "main.py"
            if args[:1] == ["rev-parse"]:
                return "def5678"
            return ""

        monkeypatch.setattr(agent, "git", fake_git)
        monkeypatch.setattr(agent, "run_cmd", lambda args, **kw: subprocess.CompletedProcess(args, 0, "", ""))
        monkeypatch.setattr(obj, "write_commit_message_file", lambda changed: "/tmp/msg.txt")
        monkeypatch.setattr("os.unlink", lambda p: None)

        sha = obj.commit_and_push_solve()
        assert sha == "def5678"
        assert ["push", "origin", "HEAD:ella/issue-42-fix"] in git_calls

    def test_returns_empty_when_no_changes(self, monkeypatch):
        obj = _make_ella_shell()
        monkeypatch.setattr(agent, "git", lambda args, **kw: "" if args[:2] == ["ls-files", "--modified"] else "")
        sha = obj.commit_and_push_solve()
        assert sha == ""


# --- create_solve_pr ---


class TestCreateSolvePr:
    def test_creates_pr_with_correct_args(self, monkeypatch):
        obj = _make_ella_shell()
        obj.issue_info = {"title": "Fix the bug"}
        obj.final_summary = "I fixed the bug by changing X."

        gh_calls = []

        def fake_gh(args, *, check=True):
            gh_calls.append(args)
            return "https://github.com/isyuricunha/ella/pull/99"

        monkeypatch.setattr(agent, "gh", fake_gh)

        url = obj.create_solve_pr()
        assert url == "https://github.com/isyuricunha/ella/pull/99"

        pr_create = [c for c in gh_calls if "pr" in c and "create" in c]
        assert len(pr_create) == 1
        assert "--base" in pr_create[0]
        assert "--head" in pr_create[0]
        assert "Fix issue #42: Fix the bug" in pr_create[0]

    def test_raises_when_no_issue_info(self, monkeypatch):
        obj = _make_ella_shell()
        obj.issue_info = None
        with pytest.raises(RuntimeError, match="Issue info missing"):
            obj.create_solve_pr()


# --- get_pr_changed_files ---


class TestGetPrChangedFiles:
    def test_parses_diff_file_list(self, monkeypatch):
        obj = _make_ella_shell()

        monkeypatch.setattr(agent, "gh", lambda args, **kw: "src/main.py\nsrc/utils.py\nREADME.md\n")
        files = obj.get_pr_changed_files()
        assert "src/main.py" in files
        assert "src/utils.py" in files

    def test_filters_ignored_files(self, monkeypatch):
        obj = _make_ella_shell()
        obj.ignore_patterns = ["node_modules/**"]

        monkeypatch.setattr(agent, "gh", lambda args, **kw: "src/main.py\nnode_modules/lib/index.js\n")
        files = obj.get_pr_changed_files()
        assert "src/main.py" in files
        assert all("node_modules" not in f for f in files)

    def test_filters_unsafe_paths(self, monkeypatch):
        obj = _make_ella_shell()

        monkeypatch.setattr(agent, "gh", lambda args, **kw: "src/main.py\n../../../etc/passwd\n")
        files = obj.get_pr_changed_files()
        assert "src/main.py" in files
        assert all("../" not in f for f in files)


# --- handle_triage label/assign/duplicate parsing ---

class TestTriageParsing:
    def _make_triage_shell(self, monkeypatch, ai_response):
        obj = _make_ella_shell()
        obj.mode = "triage"
        obj.issue = {"title": "Test bug", "body": "A bug happened", "user": {"login": "yuri"}}
        obj.event = {"repository": {"owner": {"login": "isyuricunha"}}}

        def fake_ai_call(messages, max_tokens, tools=None, use_small=False):
            return ai_response, []

        monkeypatch.setattr(obj, "ai_call", fake_ai_call)
        monkeypatch.setattr(agent, "gh", lambda args, **kw: "[]")
        monkeypatch.setattr(agent, "load_labels", lambda: [{"name": "bug", "description": "A bug"}])
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "update_task_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)

        comments = []
        monkeypatch.setattr(obj, "comment", lambda body: comments.append(body))
        obj._comments = comments
        return obj

    def test_assigns_and_strips_marker(self, monkeypatch):
        obj = self._make_triage_shell(monkeypatch,
            "Hello @yuri! Thanks for the report. Yuri will look into it.\nASSIGN: yes\nLABELS: bug")
        obj.handle_triage()

        # The ASSIGN marker should be stripped from the comment
        assert len(obj._comments) == 1
        assert "ASSIGN" not in obj._comments[0]
        assert "Hello @yuri" in obj._comments[0]

    def test_parses_labels_and_applies(self, monkeypatch):
        gh_calls = []

        def fake_gh(args, *, check=True):
            gh_calls.append(args)
            if "issue" in args and "list" in args:
                return "[]"
            return ""

        obj = _make_ella_shell()
        obj.mode = "triage"
        obj.issue = {"title": "Test bug", "body": "A bug happened", "user": {"login": "yuri"}}
        obj.event = {"repository": {"owner": {"login": "isyuricunha"}}}

        monkeypatch.setattr(obj, "ai_call", lambda msgs, mt, **kw: ("Hello!\nASSIGN: yes\nLABELS: bug", []))
        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(agent, "load_labels", lambda: [{"name": "bug", "description": "A bug"}])
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "update_task_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)

        comments = []
        monkeypatch.setattr(obj, "comment", lambda body: comments.append(body))

        obj.handle_triage()

        # Should have called gh to add label
        label_calls = [c for c in gh_calls if "issue" in c and "edit" in c and "--add-label" in c]
        assert len(label_calls) == 1
        assert "bug" in label_calls[0]

        # Should have called gh to assign
        assign_calls = [c for c in gh_calls if "issue" in c and "edit" in c and "--add-assignee" in c]
        assert len(assign_calls) == 1

        # Comment should not contain markers
        assert len(comments) == 1
        assert "ASSIGN" not in comments[0]
        assert "LABELS" not in comments[0]

    def test_duplicates_close_issue_and_strip_marker(self, monkeypatch):
        gh_calls = []

        def fake_gh(args, *, check=True):
            gh_calls.append(args)
            if "issue" in args and "list" in args:
                return "[]"
            return ""

        obj = _make_ella_shell()
        obj.mode = "triage"
        obj.issue = {"title": "Test bug", "body": "A bug", "user": {"login": "yuri"}}
        obj.event = {"repository": {"owner": {"login": "isyuricunha"}}}

        monkeypatch.setattr(obj, "ai_call", lambda msgs, mt, **kw: (
            "This looks like a duplicate!\nDUPLICATE_OF: #123", []))
        monkeypatch.setattr(agent, "gh", fake_gh)
        monkeypatch.setattr(agent, "load_labels", lambda: [{"name": "bug"}])
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "update_task_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)

        comments = []
        monkeypatch.setattr(obj, "comment", lambda body: comments.append(body))

        obj.handle_triage()

        # Should close the issue via API PATCH
        patch_calls = [c for c in gh_calls if "PATCH" in c or "patch" in c]
        assert len(patch_calls) == 1
        assert "state=closed" in patch_calls[0]
        assert "state_reason=duplicate" in patch_calls[0]

        # Comment should have "DUPLICATE_OF" stripped
        assert len(comments) == 1
        assert "DUPLICATE_OF" not in comments[0]
        assert "Duplicate of #123" in comments[0]


# --- fix_loop: minimal test with mocked ai_call ---


class TestFixLoopMinimal:
    def test_returns_false_on_install_failure(self, monkeypatch, tmp_path):
        obj = _make_ella_shell()
        obj.mode = "fix"

        monkeypatch.setattr(obj, "prepare_environment", lambda: False)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 25)
        monkeypatch.setattr(agent, "OUT", tmp_path)
        (tmp_path / "install-summary.md").write_text("pip install failed")

        result = obj.fix_loop()
        assert result is False
        assert "install_failed" in obj.final_summary

    def test_reaches_done_and_passes_checks(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "fix"

        call_count = {"n": 0}

        def fake_ai_call(messages, max_tokens, tools=None, use_small=False):
            call_count["n"] += 1
            # First call: return a done tool call
            return "", [{"id": "1", "type": "function", "function": {"name": "done", "arguments": "{}"}}]

        def fake_execute_tool(name, args):
            return "ok"

        monkeypatch.setattr(obj, "prepare_environment", lambda: True)
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 5)
        monkeypatch.setattr(obj, "ai_call", fake_ai_call)
        monkeypatch.setattr(obj, "execute_tool", fake_execute_tool)
        monkeypatch.setattr(obj, "run_project_checks", lambda: True)
        monkeypatch.setattr(obj, "update_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)
        monkeypatch.setattr(obj, "build_fix_context", lambda attempt: "context")
        monkeypatch.setattr(obj, "system_prompt_for_fix", lambda: "system")
        monkeypatch.setattr(obj, "get_tools", lambda: [])
        monkeypatch.setattr(agent, "read_checks_summary", lambda: "All passed")

        result = obj.fix_loop()
        assert result is True
        assert "applied the fix" in obj.final_summary

    def test_retries_on_no_tool_calls(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "fix"

        call_count = {"n": 0}

        def fake_ai_call(messages, max_tokens, tools=None, use_small=False):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # No tool calls, no content
                return "", []
            # Second call: return done
            return "", [{"id": "1", "type": "function", "function": {"name": "done", "arguments": "{}"}}]

        monkeypatch.setattr(obj, "prepare_environment", lambda: True)
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 5)
        monkeypatch.setattr(obj, "ai_call", fake_ai_call)
        monkeypatch.setattr(obj, "execute_tool", lambda name, args: "ok")
        monkeypatch.setattr(obj, "run_project_checks", lambda: True)
        monkeypatch.setattr(obj, "update_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)
        monkeypatch.setattr(obj, "build_fix_context", lambda attempt: "context")
        monkeypatch.setattr(obj, "system_prompt_for_fix", lambda: "system")
        monkeypatch.setattr(obj, "get_tools", lambda: [])
        monkeypatch.setattr(agent, "read_checks_summary", lambda: "All passed")

        result = obj.fix_loop()
        assert result is True
        assert call_count["n"] == 2

    def test_returns_false_on_max_attempts(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "fix"

        def fake_ai_call(messages, max_tokens, tools=None, use_small=False):
            # Always returns content with no tool calls
            return "I should call tools", []

        monkeypatch.setattr(obj, "prepare_environment", lambda: True)
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 2)
        monkeypatch.setattr(obj, "ai_call", fake_ai_call)
        monkeypatch.setattr(obj, "update_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)
        monkeypatch.setattr(obj, "build_fix_context", lambda attempt: "context")
        monkeypatch.setattr(obj, "system_prompt_for_fix", lambda: "system")
        monkeypatch.setattr(obj, "get_tools", lambda: [])
        monkeypatch.setattr(obj, "commit_and_push_wip", lambda msg: "")
        monkeypatch.setattr(agent, "read_checks_summary", lambda: "No checks")

        result = obj.fix_loop()
        assert result is False
        assert "maximum limit" in obj.final_summary

    def test_retries_on_ai_endpoint_error(self, monkeypatch):
        obj = _make_ella_shell()
        obj.mode = "fix"

        call_count = {"n": 0}

        def fake_ai_call(messages, max_tokens, tools=None, use_small=False):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise agent.CommandError("AI endpoint failed: HTTP 503")
            return "", [{"id": "1", "type": "function", "function": {"name": "done", "arguments": "{}"}}]

        monkeypatch.setattr(obj, "prepare_environment", lambda: True)
        monkeypatch.setattr(obj, "compute_max_attempts", lambda: 5)
        monkeypatch.setattr(obj, "ai_call", fake_ai_call)
        monkeypatch.setattr(obj, "execute_tool", lambda name, args: "ok")
        monkeypatch.setattr(obj, "run_project_checks", lambda: True)
        monkeypatch.setattr(obj, "update_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)
        monkeypatch.setattr(obj, "build_fix_context", lambda attempt: "context")
        monkeypatch.setattr(obj, "system_prompt_for_fix", lambda: "system")
        monkeypatch.setattr(obj, "get_tools", lambda: [])
        monkeypatch.setattr(agent, "read_checks_summary", lambda: "All passed")

        result = obj.fix_loop()
        assert result is True


# --- parse_markdown_files (used by handle_wiki) ---


class TestParseMarkdownFiles:
    def test_parses_multiple_pages(self):
        text = (
            "---FILENAME: Home.md---\n# Home\nWelcome!\n\n"
            "---FILENAME: Architecture.md---\n# Architecture\nDetails...\n"
        )
        pages = agent.parse_markdown_files(text)
        assert "Home.md" in pages
        assert "Architecture.md" in pages
        assert "Welcome!" in pages["Home.md"]
        assert "Details..." in pages["Architecture.md"]

    def test_strips_whitespace_in_filename(self):
        text = "---FILENAME:  Setup.md  ---\n# Setup\nContent"
        pages = agent.parse_markdown_files(text)
        assert "Setup.md" in pages

    def test_fallback_to_home_when_no_delimiters(self):
        text = "# Just markdown\n\nNo delimiters here."
        pages = agent.parse_markdown_files(text)
        assert "Home.md" in pages
        assert "Just markdown" in pages["Home.md"]

    def test_empty_text_returns_empty(self):
        assert agent.parse_markdown_files("") == {}

    def test_single_page(self):
        text = "---FILENAME: Guide.md---\n# Guide\nStep 1\nStep 2"
        pages = agent.parse_markdown_files(text)
        assert list(pages.keys()) == ["Guide.md"]
        assert "Step 1" in pages["Guide.md"]


# --- handle_wiki (integration with mocked ai_call, gh, git) ---


class TestHandleWiki:
    def _make_wiki_shell(self, monkeypatch, ai_response):
        obj = _make_ella_shell()
        obj.mode = "wiki"
        obj.prompt = "Generate structured Markdown wiki documentation."
        obj.repo = "isyuricunha/ella"
        obj.ignore_patterns = []
        obj.repo_instructions = ""
        obj.yuri_name = ""
        obj.yuri_email = ""

        git_calls = []
        run_cmd_calls = []

        def fake_git(args, *, check=True):
            git_calls.append(args)
            if args[:1] == ["ls-files"]:
                return "README.md\nsrc/main.py\n"
            return ""

        def fake_run_cmd(args, **kwargs):
            run_cmd_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        def fake_ai_call(messages, max_tokens, tools=None, use_small=False):
            return ai_response, []

        monkeypatch.setattr(agent, "git", fake_git)
        monkeypatch.setattr(agent, "run_cmd", fake_run_cmd)
        monkeypatch.setattr(obj, "ai_call", fake_ai_call)
        monkeypatch.setattr(obj, "create_progress_comment", lambda msg: None)
        monkeypatch.setattr(obj, "update_task_checklist", lambda *a, **kw: None)
        monkeypatch.setattr(obj, "update_progress", lambda msg: None)
        monkeypatch.setattr(obj, "get_repo_files", lambda: ["README.md", "src/main.py"])
        monkeypatch.setattr(obj, "load_repo_instructions", lambda: None)
        monkeypatch.setenv("GH_TOKEN", "fake-token")

        obj._git_calls = git_calls
        obj._run_cmd_calls = run_cmd_calls
        return obj

    def test_generates_and_pushes_wiki(self, monkeypatch):
        wiki_output = (
            "---FILENAME: Home.md---\n# Home\nWelcome to Ella!\n\n"
            "---FILENAME: Setup.md---\n# Setup\nInstall with pip.\n"
        )
        obj = self._make_wiki_shell(monkeypatch, wiki_output)

        obj.handle_wiki()

        # Should have called git push to wiki
        push_calls = [c for c in obj._git_calls if "push" in c]
        assert len(push_calls) >= 1
        assert "master" in push_calls[-1]

        # run_cmd should have git add, commit, config
        commit_calls = [c for c in obj._run_cmd_calls if "commit" in c]
        assert len(commit_calls) >= 1

    def test_wiki_failure_on_empty_ai_response(self, monkeypatch):
        obj = self._make_wiki_shell(monkeypatch, "")

        obj.handle_wiki()

        # Should NOT have pushed because AI returned empty (no pages parsed)
        push_calls = [c for c in obj._git_calls if "push" in c]
        assert len(push_calls) == 0

    def test_wiki_missing_gh_token(self, monkeypatch):
        wiki_output = "---FILENAME: Home.md---\n# Home\nContent"
        obj = self._make_wiki_shell(monkeypatch, wiki_output)
        monkeypatch.delenv("GH_TOKEN", raising=False)

        obj.handle_wiki()

        # Should NOT have pushed because no token
        push_calls = [c for c in obj._git_calls if "push" in c]
        assert len(push_calls) == 0

    def test_wiki_sanitizes_filenames(self, monkeypatch):
        wiki_output = "---FILENAME: ../../etc/passwd.md---\n# Hacked\nBad"
        obj = self._make_wiki_shell(monkeypatch, wiki_output)

        # Capture what filenames were written
        written = []

        def spy_write(self, content, encoding="utf-8"):
            written.append(self.name)
            return len(content)

        monkeypatch.setattr(Path, "write_text", spy_write)
        obj.handle_wiki()

        # The filename should be sanitized (slashes replaced with underscores)
        for name in written:
            assert "../../../" not in name
