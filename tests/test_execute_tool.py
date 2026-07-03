"""Tests for execute_tool happy paths: search_code, read_file, edit_file.

These tests create a temporary git repository, patch ROOT/ROOT_RESOLVED
to point at it, and exercise the tools with real files.
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
    obj.yuri_name = ""
    obj.yuri_email = ""
    return obj


@pytest.fixture
def temp_repo(tmp_path, monkeypatch):
    """Create a temp git repo with sample files and patch ROOT/ROOT_RESOLVED."""
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text(
        'def hello():\n'
        '    print("hello world")\n',
        encoding="utf-8",
    )
    (repo / "README.md").write_text(
        "# Test Repo\n\nA test repository.\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "init"], cwd=repo, check=True,
                   capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True,
                   capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial commit"],
        cwd=repo, check=True, capture_output=True,
        env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com",
             "HOME": str(tmp_path)},
    )

    monkeypatch.setattr(agent, "ROOT", repo)
    monkeypatch.setattr(agent, "ROOT_RESOLVED", repo.resolve())
    return repo


class TestSearchCode:
    def test_finds_match(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool(
            "search_code", json.dumps({"query": "hello world"}))
        assert "hello world" in result
        assert "src/main.py" in result

    def test_no_match(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool(
            "search_code", json.dumps({"query": "nonexistent_function_xyz"}))
        assert "No results" in result

    def test_empty_query(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool(
            "search_code", json.dumps({"query": ""}))
        assert "required" in result.lower()


class TestReadFile:
    def test_reads_existing_file(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool(
            "read_file", json.dumps({"filepath": "src/main.py"}))
        assert "def hello" in result
        assert "print" in result

    def test_file_not_found(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool(
            "read_file", json.dumps({"filepath": "nonexistent.py"}))
        assert "not found" in result

    def test_rejects_path_outside_repo(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool(
            "read_file", json.dumps({"filepath": "../../../etc/passwd"}))
        assert "denied" in result.lower() or "invalid" in result.lower()


class TestEditFile:
    def test_edits_existing_file(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool("edit_file", json.dumps({
            "filepath": "src/main.py",
            "search_text": 'print("hello world")',
            "replace_text": 'print("goodbye world")',
        }))
        assert "Successfully edited" in result
        content = (temp_repo / "src" / "main.py").read_text()
        assert "goodbye world" in content
        assert "hello world" not in content

    def test_file_not_found(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool("edit_file", json.dumps({
            "filepath": "nonexistent.py",
            "search_text": "foo",
            "replace_text": "bar",
        }))
        assert "not found" in result

    def test_search_text_not_in_file(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool("edit_file", json.dumps({
            "filepath": "src/main.py",
            "search_text": "this_does_not_exist",
            "replace_text": "replacement",
        }))
        assert "not found in file" in result

    def test_non_unique_search_text(self, temp_repo):
        (temp_repo / "dups.py").write_text(
            "x = 1\nx = 1\n", encoding="utf-8")
        ella = _make_ella_shell()
        result = ella.execute_tool("edit_file", json.dumps({
            "filepath": "dups.py",
            "search_text": "x = 1",
            "replace_text": "x = 2",
        }))
        assert "not unique" in result

    def test_rejects_path_outside_repo(self, temp_repo):
        ella = _make_ella_shell()
        result = ella.execute_tool("edit_file", json.dumps({
            "filepath": "../../../etc/passwd",
            "search_text": "foo",
            "replace_text": "bar",
        }))
        assert "denied" in result.lower() or "invalid" in result.lower()
