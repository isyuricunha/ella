#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
ROOT_RESOLVED = ROOT.resolve()
AGENT_DIR = Path(__file__).parent.resolve()
RUNNER_TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
OUT = RUNNER_TEMP / "ella-output"
OUT.mkdir(parents=True, exist_ok=True)

SAFE_LABELS_DEFAULT = [
    {"name": "bug", "color": "d73a4a", "description": "Something is not working"},
    {"name": "enhancement", "color": "a2eeef",
        "description": "New feature or request"},
    {"name": "documentation", "color": "0075ca",
        "description": "Improvements or additions to documentation"},
    {"name": "dependencies", "color": "0366d6",
        "description": "Dependency updates or package changes"},
    {"name": "security", "color": "b60205",
        "description": "Security related changes"},
    {"name": "performance", "color": "fbca04",
        "description": "Performance related changes"},
    {"name": "refactor", "color": "cfd3d7",
        "description": "Code refactoring without behavior changes"},
    {"name": "tests", "color": "0e8a16", "description": "Testing related changes"},
    {"name": "ui", "color": "c2e0c6", "description": "User interface related changes"},
    {"name": "frontend", "color": "1d76db",
        "description": "Frontend related changes"},
    {"name": "backend", "color": "5319e7", "description": "Backend related changes"},
    {"name": "i18n", "color": "bfd4f2",
        "description": "Internationalization or localization"},
    {"name": "ci", "color": "fef2c0", "description": "CI/CD or workflow changes"},
    {"name": "chore", "color": "ededed", "description": "Maintenance or cleanup"},
    {"name": "question", "color": "d876e3",
        "description": "Further information is requested"},
    {"name": "good first issue", "color": "7057ff",
        "description": "Good for newcomers"},
    {"name": "help wanted", "color": "008672",
        "description": "Extra attention is needed"},
]

DEFAULT_IGNORE = [
    ".git/**",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "**/node_modules/**",
    "**/.next/**",
    "**/dist/**",
    "**/build/**",
    "**/coverage/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.ruff_cache/**",
    "**/target/**",
    "**/bin/**",
    "**/obj/**",
    "**/*.generated.*",
    "**/*.min.js",
    "**/*.map",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "bun.lockb",
    "Cargo.lock",
    "poetry.lock",
    "uv.lock",
]


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


TIME_LIMIT_SECONDS = env_int("ELLA_TIME_LIMIT_SECONDS", 3600)

COMMIT_SUBJECT_RE = re.compile(
    r"^(build|chore|ci|docs|feat|fix|perf|refactor|revert|audit|security|style|test)(\([a-z0-9._/-]+\))?!?: .+"
)

MAX_CONTEXT_PR_DIFF_BYTES = env_int("ELLA_MAX_CONTEXT_PR_DIFF_BYTES", 500_000)
MAX_CONTEXT_FILE_BYTES = env_int("ELLA_MAX_CONTEXT_FILE_BYTES", 120_000)
MAX_CONTEXT_REQUESTED_FILE_BYTES = env_int(
    "ELLA_MAX_CONTEXT_REQUESTED_FILE_BYTES", 250_000)
MAX_CONTEXT_REPO_FILES_BYTES = env_int(
    "ELLA_MAX_CONTEXT_REPO_FILES_BYTES", 200_000)

MAX_TOKENS = {
    "ask": env_int("ELLA_MAX_TOKENS_ASK", 2048),
    "pr": env_int("ELLA_MAX_TOKENS_PR", 4096),
    "review": env_int("ELLA_MAX_TOKENS_REVIEW", 4096),
    "plan": env_int("ELLA_MAX_TOKENS_PLAN", 4096),
    "label": env_int("ELLA_MAX_TOKENS_LABEL", 1200),
    "fix": env_int("ELLA_MAX_TOKENS_FIX", 16384),
    "continue": env_int("ELLA_MAX_TOKENS_CONTINUE", 16384),
    "solve": env_int("ELLA_MAX_TOKENS_SOLVE", 16384),
    "heal": env_int("ELLA_MAX_TOKENS_HEAL", 16384),
    "triage": env_int("ELLA_MAX_TOKENS_TRIAGE", 8192),
    "quote": env_int("ELLA_MAX_TOKENS_QUOTE", 1024),
}


class CommandError(Exception):
    pass


def scrub_secrets(text: str) -> str:
    if not isinstance(text, str):
        return text

    secrets_to_mask = [
        "GH_TOKEN", "GITHUB_TOKEN",
        "ELLA_AI_API_KEY",
        "ELLA_AI_BASE_URL",
        "ELLA_AI_MODEL",
        "ELLA_AI_SMALL_API_KEY",
        "ELLA_AI_SMALL_BASE_URL",
        "ELLA_AI_SMALL_MODEL",
        "ELLA_APP_PRIVATE_KEY", "ELLA_APP_CLIENT_ID",
    ]

    for key in secrets_to_mask:
        secret = os.environ.get(key)
        if secret and len(secret) >= 3:
            text = text.replace(secret, "***REDACTED***")

    # Also redact generic GitHub tokens pattern
    text = re.sub(r'gh[ps]_[a-zA-Z0-9]{36}', '***REDACTED***', text)
    # Redact ghp_ tokens (classic PATs)
    text = re.sub(r'github_pat_[a-zA-Z0-9_]{22,}', '***REDACTED***', text)
    return text


def write_debug(name: str, text: str) -> None:
    safe_text = scrub_secrets(text)
    (OUT / name).write_text(safe_text, encoding="utf-8", errors="replace")


def read_checks_summary() -> str:
    path = OUT / "checks-summary.md"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def read_pr_diff_limited() -> str:
    path = OUT / "pr-diff-limited.txt"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def read_text_limited(path: Path, limit: int) -> str:
    try:
        with path.open("rb") as f:
            data = f.read(limit)
        text = data.decode("utf-8", errors="replace")
        if path.stat().st_size > limit:
            text += "\n\n[truncated]\n"
        return text
    except FileNotFoundError:
        return ""


def run_cmd(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    cwd: Path | None = None,
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cwd = ROOT if cwd is None else cwd
    if capture:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=env,
        )
    else:
        result = subprocess.run(args, cwd=cwd, text=True,
                                timeout=timeout, env=env)

    if check and result.returncode != 0:
        output = result.stdout if capture else ""
        error_msg = f"Command failed: {' '.join(args)}\n{output}"
        
        # Security patch: Redact known secrets from exception message to avoid leaking tokens
        error_msg = scrub_secrets(error_msg)

        raise CommandError(error_msg)
    return result


def gh(args: list[str], *, check: bool = True) -> str:
    result = run_cmd(["gh", *args], check=check, capture=True, timeout=120)
    return result.stdout


def git(args: list[str], *, check: bool = True) -> str:
    result = run_cmd(["git", *args], check=check, capture=True, timeout=900)
    return result.stdout


def clean_env_for_checks() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("ELLA_AI_"):
            env.pop(key, None)
        if key.startswith("ELLA_APP_"):
            env.pop(key, None)
        if key.startswith("YURI_"):
            env.pop(key, None)
        if key in {"GH_TOKEN", "GITHUB_TOKEN",
                   "ELLA_APP_PRIVATE_KEY", "ELLA_APP_CLIENT_ID",
                   "GITHUB_EVENT_PATH"}:
            env.pop(key, None)
    env["CI"] = "true"
    return env


def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _strip_tool_call_json(text: str) -> str:
    """Remove raw tool-call syntax that some models emit in text mode.

    When no tools are provided in the API request, certain models
    still hallucinate tool-call syntax in the text content. Handles
    JSON-style and XML-style tag formats.
    """
    import re as _re

    # 1. JSON-style: {"tool": "read_file", ...}
    cleaned = _re.sub(r'^\s*\{"tool"\s*:.*?\}\s*$', '', text, flags=_re.MULTILINE)
    cleaned = _re.sub(r'\n+\{"tool"\s*:.*?\}\s*$', '', cleaned, flags=_re.DOTALL)

    # 2. XML-style tag hallucinations (specific known tags)
    xml_markers = [
        r"<tool_call>",
        r"</tool_call>",
        r"<arg_key\b",
        r"</arg_key>",
        r"<arg_value\b",
        r"</arg_value>",
        r"<command\b",
        r"</command>",
        r"<description\b",
        r"</description>",
        r"</result>",
        r"<maid\b",
        r"</maid>",
        r"</think>",
    ]
    pattern = '|'.join(xml_markers)
    m = _re.search(pattern, cleaned)
    if m:
        cleaned = cleaned[:m.start()].rstrip()

    # 2b. Generic self-closing XML tool-call tags: <read_file ... />, <list_issues />, etc.
    # Only match snake_case tag names (tool names), not HTML tags like <br/> or <img/>
    cleaned = _re.sub(r'\n\s*<[a-z]+(?:_[a-z]+)+\b[^>]*/>\s*', '', cleaned, flags=_re.IGNORECASE)
    cleaned = _re.sub(r'\s*<[a-z]+(?:_[a-z]+)+\b[^>]*/>', '', cleaned, flags=_re.IGNORECASE)

    # 2c. Generic XML open/close tool-call tags: <read_file>...</read_file>
    # Match tool-name-style tags (snake_case) that the model hallucinates
    cleaned = _re.sub(r'\n?\s*<([a-z]+(?:_[a-z]+)+)\b[^>]*>.*?</\1>\s*$', '', cleaned, flags=_re.DOTALL | _re.IGNORECASE)
    # Also cut from any standalone snake_case open tag to end of text
    m2 = _re.search(r'\n\s*<[a-z]+(?:_[a-z]+)+\b', cleaned, _re.IGNORECASE)
    if m2:
        cleaned = cleaned[:m2.start()].rstrip()

    # 3. Strip trailing shell/code fences from hallucinated output
    cleaned = _re.sub(r'\n+```(?:shell|bash|sh)?\s*\n.*?\n```\s*$', '', cleaned, flags=_re.DOTALL)

    cleaned = cleaned.strip()
    if not cleaned:
        return "I could not generate a response. Please try rephrasing your request."
    return cleaned


def _pyproject_has_build_target(path: Path) -> bool:
    """Check if a pyproject.toml defines a buildable Python package.

    Returns False for projects that only use pyproject.toml as config
    (e.g., pytest settings) without any installable code. This prevents
    'pip install -e .' from failing on hatchling/setuptools with no packages.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if "[project]" in text and "dependencies = [" in text:
        return True
    if "[tool.hatch.build" in text and "packages = []" not in text:
        return True
    if "build-backend" in text and "[build-system]" in text and "packages = []" not in text:
        return True
    return False


def safe_rel_path(path: str) -> bool:
    p = Path(path)
    if not path.strip():
        return False
    if "\x00" in path:
        return False
    if p.is_absolute():
        return False
    if ".." in p.parts:
        return False
    if p.parts and p.parts[0] == ".git":
        return False
    return True


def load_ignore_patterns() -> list[str]:
    patterns = list(DEFAULT_IGNORE)
    custom = AGENT_DIR / "ignore"
    if custom.exists():
        for line in custom.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


def is_ignored(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        p = pattern.strip().replace("\\", "/")
        if not p:
            continue
        if fnmatch.fnmatch(normalized, p):
            return True
        if p.endswith("/**") and normalized.startswith(p[:-3]):
            return True
        if "/" not in p and fnmatch.fnmatch(Path(normalized).name, p):
            return True
    return False


def load_labels() -> list[dict[str, str]]:
    labels_path = AGENT_DIR / "labels.json"
    if not labels_path.exists():
        return SAFE_LABELS_DEFAULT

    try:
        data = json.loads(labels_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return SAFE_LABELS_DEFAULT
        labels: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            labels.append(
                {
                    "name": name,
                    "color": str(item.get("color", "ededed")).strip().lstrip("#")[:6] or "ededed",
                    "description": str(item.get("description", "")).strip()[:100],
                }
            )
        return labels or SAFE_LABELS_DEFAULT
    except Exception:
        return SAFE_LABELS_DEFAULT


def parse_jsonish(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(raw[start: end + 1])


def parse_markdown_files(text: str) -> dict[str, str]:
    files = {}
    current_file = None
    current_content = []
    
    for line in text.splitlines():
        match = re.match(r"^---FILENAME:\s*(.+?)\s*---$", line.strip())
        if match:
            if current_file:
                files[current_file] = "\n".join(current_content).strip()
            current_file = match.group(1)
            current_content = []
        elif current_file is not None:
            current_content.append(line)
            
    if current_file:
        files[current_file] = "\n".join(current_content).strip()
        
    if not files and text.strip():
        # Fallback if the LLM completely ignored the delimiter instructions
        return {"Home.md": text.strip()}
        
    return files



def tail_text(path: Path, lines: int = 100) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


class Ella:
    def __init__(self) -> None:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise RuntimeError("GITHUB_EVENT_PATH is missing")

        try:
            self.event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to read or parse event file: {e}")
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.run_id = os.environ.get("GITHUB_RUN_ID", "") or f"local{int(time.time()) % 1000000}"
        self.issue_number = -1
        self.issue = self.event.get("issue", {})
        if "issue" in self.event:
            self.issue_number = int(self.issue["number"])
        elif "pull_request" in self.event:
            self.issue_number = int(self.event["pull_request"]["number"])
        self.comment_event = self.event.get("comment", {})
        self.comment_id = int(self.comment_event.get("id", 0))
        self.is_pr = "pull_request" in self.event or "pull_request" in self.issue
        repo = self.event.get("repository", {}) or {}
        self.default_branch = repo.get("default_branch") or "main"

        self.mode = "unknown"
        self.prompt = ""
        self.progress_comment_id: str | None = None
        self.pr_info: dict[str, Any] | None = None
        self.issue_info: dict[str, Any] | None = None
        self.allowed_files: list[str] = []
        self.ignore_patterns = load_ignore_patterns()
        self.max_attempts = self.compute_max_attempts()

        self.ai_base_url = os.environ.get("ELLA_AI_BASE_URL", "").strip()
        self.ai_model = os.environ.get("ELLA_AI_MODEL", "").strip()
        self.ai_api_key = os.environ.get("ELLA_AI_API_KEY", "").strip()

        self.ai_small_model = os.environ.get("ELLA_AI_SMALL_MODEL", "").strip() or self.ai_model
        self.ai_small_base_url = os.environ.get("ELLA_AI_SMALL_BASE_URL", "").strip() or self.ai_base_url
        self.ai_small_api_key = os.environ.get("ELLA_AI_SMALL_API_KEY", "").strip() or self.ai_api_key

        self.commit_name = "Ella Mizuki"
        self.commit_email = "290269138+ella-mizuki[bot]@users.noreply.github.com"
        
        self.yuri_name = os.environ.get("YURI_COMMIT_NAME", "").strip()
        self.yuri_email = os.environ.get("YURI_COMMIT_EMAIL", "").strip()

        self.feedback = ""
        self.extra_context = ""
        self.final_summary = ""

    def run(self) -> None:
        self.mask_secrets()

        # Prevent infinite loops: Do not respond to bots (including herself)
        if self.comment_id:
            user_login = self.comment_event.get("user", {}).get("login", "")
            if not user_login:
                raise RuntimeError("User login not found in comment event")
            if "[bot]" in user_login or user_login == "ella-mizuki[bot]":
                print(f"Skipping: ignoring comment from bot {user_login}")
                sys.exit(0)

            # Restrict usage to repository owner
            repo_owner = self.event.get("repository", {}).get("owner", {}).get("login", "")
            if not repo_owner:
                raise RuntimeError("Repository owner not found in event")
            if user_login != repo_owner:
                print(f"Skipping: ignoring comment from unauthorized user {user_login}. Only repo owner can use the bot.")
                sys.exit(0)

        if self.comment_id:
            self.react("eyes")
        self.parse_command()

        handler = self._dispatch.get(self.mode)
        if handler:
            handler(self)
            return

        self.comment("I do not recognize that command. Use `/ella help`.")
        self.react("confused")

    # --- Pre-dispatch validation shared by AI modes ---

    def _validate_and_load_context(self) -> str | None:
        """Shared validation for modes that need AI config and PR/issue context.

        Returns an error message string if validation fails, or None if OK.
        """
        self.validate_ai_config()

        pr_only = {"pr", "review", "fix", "continue"}
        issue_only = {"plan", "label", "solve"}

        if (not self.is_pr) and self.mode in pr_only:
            return "That command needs to be used inside a PR."

        if self.is_pr and self.mode == "solve":
            return "Use `/ella fix` inside a PR. Use `/ella solve` on an issue."

        if self.is_pr and self.mode in (pr_only | issue_only) - {"solve"}:
            self.load_pr_metadata()
            if self.mode == "review" and not self.comment_id and self.pr_info and self.pr_info.get("isDraft"):
                print("Skipping review: PR is in draft state")
                return "__skip__"

        if (not self.is_pr) and self.mode in issue_only:
            self.load_issue_metadata()

        return None

    # --- Mode handlers ---

    def _handle_wiki(self) -> None:
        try:
            self.handle_wiki()
        except Exception as exc:
            print(f"AI call failed during wiki: {exc}")
            self.comment("❌ I could not generate the wiki. The AI endpoint returned an error.")
            self.react("confused")

    def _handle_triage(self) -> None:
        issue_author = self.issue.get("user", {}).get("login", "")
        if "[bot]" in issue_author or issue_author == "ella-mizuki[bot]":
            print(f"Skipping triage: issue created by bot {issue_author}")
            return
        self.validate_ai_config()
        self.load_repo_instructions()
        self.handle_triage()

    def _handle_help(self) -> None:
        self.comment(self.help_text())
        self.react("+1")

    def _handle_read_only(self) -> None:
        error = self._validate_and_load_context()
        if error:
            if error != "__skip__":
                self.comment(error)
                self.react("confused")
            return
        try:
            response = self.handle_read_only()
        except Exception as exc:
            print(f"AI call failed during {self.mode}: {exc}")
            self.comment("❌ I could not generate a response. The AI endpoint returned an error.")
            self.react("confused")
            return
        if self.mode == "review":
            try:
                data = parse_jsonish(response)
                summary = data.get("summary", "")
                comments = data.get("comments", [])
                if summary or comments:
                    self.post_inline_review(summary, comments)
                    self.react("+1")
                    return
            except Exception as e:
                print(f"Failed to parse review JSON: {e}")
                self.comment("I tried to post an inline review but could not parse the model response as valid JSON. Here is the raw output:\n\n" + response)
                self.react("confused")
                return
        self.comment(response)
        self.react("+1")

    def _handle_label(self) -> None:
        error = self._validate_and_load_context()
        if error:
            if error != "__skip__":
                self.comment(error)
                self.react("confused")
            return
        try:
            self.handle_label()
        except Exception as exc:
            print(f"AI call failed during label: {exc}")
            self.comment("❌ I could not classify labels. The AI endpoint returned an error.")
            self.react("confused")
            return
        self.react("+1")

    def _handle_fix(self) -> None:
        error = self._validate_and_load_context()
        if error:
            if error != "__skip__":
                self.comment(error)
                self.react("confused")
            return
        if self.pr_info and self.pr_info.get("isCrossRepository") is True:
            self.comment(
                "For security reasons, I can only commit to branches inside this repository. If you are an external contributor, please ask a maintainer to pull your branch here first!")
            self.react("confused")
            return
        self.checkout_pr_branch()
        self.load_repo_instructions()
        self.allowed_files = self.get_pr_changed_files()
        self.create_progress_comment(
            self.generate_message(
                "I'm diving into this PR. Write 1-2 friendly sentences saying I'll investigate and report back. No headers.",
                fallback="I started investigating this PR and will report back soon."
            )
            + f"\n\n**Limits:** {self.max_attempts} turns | {TIME_LIMIT_SECONDS // 60} minutes"
        )
        success = self.fix_loop()
        if success:
            commit_sha = self.commit_and_push_fix()
            if commit_sha:
                msg = self.generate_message(
                    f"I just fixed a PR (commit {commit_sha}). Summary: {self.final_summary}. Write 2-3 friendly sentences referencing the commit. No headers.",
                    fallback=f"I applied the fix and committed it.\n\nCommit: `{commit_sha}`\n\n{self.final_summary}"
                )
                self.comment(msg)
                self.react("rocket")
            else:
                msg = self.generate_message(
                    f"All checks passed, no code changes needed. Summary: {self.final_summary}. Write 2-3 friendly sentences. No headers.",
                    fallback=f"All checks passed and no changes were needed.\n\n{self.final_summary}"
                )
                self.comment(msg)
                self.react("rocket")
        else:
            self.comment(self.final_summary)
            self.react("confused")

    def _handle_solve(self) -> None:
        error = self._validate_and_load_context()
        if error:
            if error != "__skip__":
                self.comment(error)
                self.react("confused")
            return
        self.checkout_solve_branch()
        self.load_repo_instructions()
        self.allowed_files = self.get_repo_files()
        self.create_progress_comment(
            self.generate_message(
                "I'm setting up a branch for this issue. Write 1-2 friendly sentences saying I'll dive in and report back. No headers.",
                fallback="I started working on this issue and will report back soon."
            )
            + f"\n\n**Limits:** {self.max_attempts} turns | {TIME_LIMIT_SECONDS // 60} minutes"
        )
        success = self.fix_loop()
        if success:
            commit_sha = self.commit_and_push_solve()
            if commit_sha:
                pr_url = self.create_solve_pr()
                msg = self.generate_message(
                    f"I solved an issue and opened a PR ({pr_url}, commit {commit_sha}). Summary: {self.final_summary}. Write 2-3 friendly sentences referencing the PR and commit. No headers.",
                    fallback=f"I created a PR for this issue.\n\nPR: {pr_url}\nCommit: `{commit_sha}`"
                )
                self.comment(msg)
                self.react("rocket")
            else:
                msg = self.generate_message(
                    f"All checks passed, no code changes needed. Summary: {self.final_summary}. Write 2-3 friendly sentences. No headers.",
                    fallback=f"All checks passed but no changes were needed.\n\n{self.final_summary}"
                )
                self.comment(msg)
                self.react("rocket")
        else:
            self.comment(self.final_summary)
            self.react("confused")

    def _handle_heal(self) -> None:
        self.handle_heal()

    def _handle_quote(self) -> None:
        """Generate a short quote via the small model, rewrite README, commit, push."""
        self.validate_ai_config()
        system = (
            "Generate one short quote of the week for a developer's GitHub profile README. "
            "Requirements: a single line, 5-15 words, motivational or reflective. "
            "No politics, no attribution, no markdown, no first person. "
            "All lowercase, no trailing period. Output just the sentence."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": self.prompt or
                "Generate a short uplifting quote of the week for a developer's GitHub profile README."},
        ]
        try:
            content, _ = self.ai_call(messages, MAX_TOKENS["quote"], use_small=True)
        except Exception as exc:
            print(f"AI call failed during quote: {exc}")
            return

        quote = self._sanitize_quote(content or "")
        if not quote:
            print("Quote generation produced no usable output; skipping commit.")
            return

        self._rewrite_readme_quote(quote)
        self._commit_readme()

    @staticmethod
    def _sanitize_quote(raw: str) -> str:
        s = raw.strip()
        if s.startswith("```"):
            s = s.strip("`")
            lines = [l for l in s.splitlines()
                     if not l.strip().startswith(("python", "text", "markdown"))]
            s = "\n".join(lines).strip()
        line = next((l.strip() for l in s.splitlines() if l.strip()), "")
        line = line.strip(' ""`')
        line = line.lower()
        if len(line) > 140:
            line = line[:137].rstrip() + "..."
        return line

    @staticmethod
    def _rewrite_readme_quote(quote: str) -> None:
        path = Path("README.md")
        readme = path.read_text(encoding="utf-8") if path.exists() else ""
        marker = "**a sentence to brighten your day:**<br>"
        new_block = f"{marker}\n    {quote}\n"
        if marker in readme:
            before = readme.split(marker, 1)[0]
            readme = before + new_block + "\n"
        else:
            readme = readme.rstrip("\n") + "\n\n" + new_block + "\n"
        path.write_text(readme, encoding="utf-8")

    def _commit_readme(self) -> None:
        name = self.yuri_name or self.commit_name
        email = self.yuri_email or self.commit_email
        git(["config", "user.name", name])
        git(["config", "user.email", email])
        changed = git(["ls-files", "--modified", "--others", "--exclude-standard"],
                      check=False).splitlines()
        if "README.md" not in changed:
            print("No README changes to commit.")
            return
        git(["add", "README.md"])
        git(["commit", "--no-verify", "-m", "update week quote"])
        git(["push", "origin", f"HEAD:{self.default_branch}"])

    # --- Dispatch table ---
    _dispatch: dict[str, Any] = {
        "wiki": _handle_wiki,
        "triage": _handle_triage,
        "help": _handle_help,
        "ask": _handle_read_only,
        "pr": _handle_read_only,
        "review": _handle_read_only,
        "plan": _handle_read_only,
        "label": _handle_label,
        "fix": _handle_fix,
        "continue": _handle_fix,
        "solve": _handle_solve,
        "heal": _handle_heal,
        "quote": _handle_quote,
    }

    def mask_secrets(self) -> None:
        secrets = [
            "GH_TOKEN", "GITHUB_TOKEN",
            "ELLA_AI_BASE_URL",
            "ELLA_AI_MODEL",
            "ELLA_AI_API_KEY",
            "ELLA_AI_SMALL_BASE_URL",
            "ELLA_AI_SMALL_MODEL",
            "ELLA_AI_SMALL_API_KEY",
            "ELLA_APP_PRIVATE_KEY", "ELLA_APP_CLIENT_ID",
            "YURI_COMMIT_NAME", "YURI_COMMIT_EMAIL",
        ]
        for secret in secrets:
            value = os.environ.get(secret, "")
            if value:
                print(f"::add-mask::{value}")

    def parse_command(self) -> None:
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        if event_name == "issues" and self.event.get("action") == "opened":
            self.mode = "triage"
            self.prompt = ""
            return
            
        if event_name == "workflow_run" and self.event.get("action") == "completed":
            self.mode = "heal"
            self.prompt = ""
            return

        if event_name in {"schedule", "workflow_dispatch"}:
            self.mode = "quote"
            self.prompt = "Generate a short uplifting quote of the week for a developer's GitHub profile README."
            return

        if event_name in {"pull_request", "pull_request_target"} and self.event.get("action") in {"opened", "synchronize"}:
            self.mode = "review"
            self.prompt = "Please perform a thorough code review of this PR."
            return

        body = str(self.comment_event.get("body", "")).strip()
        commands = [
            ("help", r"(?:^|\s)/ella\s+help"),
            ("continue", r"(?:^|\s)/ella\s+continue"),
            ("review", r"(?:^|\s)/ella\s+review"),
            ("label", r"(?:^|\s)/ella\s+label"),
            ("solve", r"(?:^|\s)/ella\s+solve"),
            ("wiki", r"(?:^|\s)/ella\s+wiki"),
            ("plan", r"(?:^|\s)/ella\s+plan"),
            ("fix", r"(?:^|\s)/ella\s+fix"),
            ("ask", r"(?:^|\s)/ella\s+ask"),
            ("pr", r"(?:^|\s)/ella\s+pr"),
        ]

        self.mode = "unknown"
        self.prompt = ""

        for mode, pattern in commands:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                self.mode = mode
                self.prompt = body[match.end():].strip()
                break

        defaults = {
            "ask": "Reply with one short sentence confirming everything works.",
            "pr": "Briefly analyze this PR: what changed, risks, and whether it's safe to merge.",
            "review": "Review this PR for bugs, security, type issues, and missing tests.",
            "plan": "Write a short, practical implementation plan. Don't edit any files.",
            "label": "Classify this issue or PR with the most relevant labels.",
            "fix": "Fix the issue described here. Keep changes minimal and safe.",
            "continue": "Keep trying to fix this PR with minimal, safe changes.",
            "solve": "Solve this issue with the smallest safe change possible.",
            "wiki": "Generate structured Markdown wiki documentation for this repository.",
        }

        if self.mode in defaults and not self.prompt:
            self.prompt = defaults[self.mode]

        write_debug("command.json", json.dumps(
            {"mode": self.mode, "prompt": self.prompt}, indent=2))

    def validate_ai_config(self) -> None:
        missing = []
        if not self.ai_base_url:
            missing.append("ELLA_AI_BASE_URL")
        if not self.ai_model:
            missing.append("ELLA_AI_MODEL")
        if not self.ai_api_key:
            missing.append("ELLA_AI_API_KEY")
        if missing:
            raise RuntimeError(
                "Missing required secrets: " + ", ".join(missing))

    def help_text(self) -> str:
        return """Hey! I'm Ella - here's what I can do:

`/ella help`
I list my commands (you're looking at it).

`/ella ask your question`
I answer based on the issue or PR context.

`/ella pr request`
I give you a quick PR summary - changes, risks, merge readiness.

`/ella review request`
I do a thorough code review. Also runs automatically on PR open/synchronize (skips drafts).

`/ella plan request`
I write an implementation plan without touching any files.

`/ella label`
I apply the most relevant labels to the issue or PR.

`/ella wiki`
I read the whole codebase and generate a multi-page GitHub Wiki.

`/ella fix request`
I fix the PR, run checks, and commit directly to the branch.

`/ella continue request`
I keep trying to fix the PR if the previous attempt hit a limit.

`/ella solve request`
On an issue, I create a branch, fix it, run checks, and open a PR.

**Quote of the week** (automated):
Triggered by `workflow_dispatch` or `schedule` - not a comment. I write a fresh quote, update the README, and commit."""

    def react(self, content: str) -> None:
        try:
            gh([
                "api",
                "--method",
                "POST",
                f"repos/{self.repo}/issues/comments/{self.comment_id}/reactions",
                "-H",
                "Accept: application/vnd.github+json",
                "-f",
                f"content={content}",
            ], check=False)
        except Exception:
            pass

    def comment(self, body: str) -> None:
        gh(["issue", "comment", str(self.issue_number),
           "--repo", self.repo, "--body", scrub_secrets(body)])

    def create_progress_comment(self, body: str) -> None:
        out = gh([
            "api",
            "--method",
            "POST",
            f"repos/{self.repo}/issues/{self.issue_number}/comments",
            "-f",
            f"body={scrub_secrets(body)}",
            "--jq",
            ".id",
        ])
        self.progress_comment_id = out.strip()

    def update_progress(self, body: str) -> None:
        if not self.progress_comment_id:
            print("Warning: progress comment not posted (no progress_comment_id); update skipped")
            return
        try:
            gh([
                "api",
                "--method",
                "PATCH",
                f"repos/{self.repo}/issues/comments/{self.progress_comment_id}",
                "-f",
                f"body={scrub_secrets(body)}",
            ], check=True)
        except Exception as e:
            print(f"Warning: failed to update progress comment: {e}")

    def generate_message(self, prompt: str, fallback: str, max_tokens: int = 300) -> str:
        """Generate a short natural message using the small model.

        Returns the AI-generated text, or ``fallback`` if the AI call fails
        or the output looks like leaked reasoning instead of a message.
        """
        system = (
            "You are Ella Mizuki, a charismatic female AI assistant. The repository owner is Yuri. "
            "You are not Yuri - you are Ella. "
            "Respond with ONLY the message text. No reasoning, no analysis. "
            "Write in English with a warm, charismatic tone using first-person ('I'). "
            "Be concise (1-3 sentences). No markdown headers or code fences."
        )
        try:
            text, _ = self.ai_call(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                use_small=True,
            )
            if not text or not text.strip():
                return fallback

            text = text.strip()

            # Safety net: if the model still leaked reasoning (long output
            # with reasoning markers), fall back to the template.
            lines = text.splitlines()
            if len(lines) > 6:
                print("generate_message: output too long, using fallback")
                return fallback

            reasoning_prefixes = ("Let me", "Let's", "We are", "I need to", "I should",
                                  "Since", "However", "But note", "Note:", "The user")
            clean_lines = [l for l in lines if not l.strip().startswith(reasoning_prefixes)]
            if clean_lines and len(clean_lines) < len(lines):
                text = "\n".join(clean_lines).strip()

            return text or fallback
        except Exception as exc:
            print(f"generate_message fallback ({exc})")
            return fallback

    def update_task_checklist(self, title: str, steps: list[tuple[str, bool]], detail: str = "") -> None:
        lines = [f"### 🤖 {title}\n"]
        for step_name, is_done in steps:
            lines.append(f"- [{'x' if is_done else ' '}] {step_name}")
        if detail:
            lines.append(f"\n> {detail}")
        self.update_progress("\n".join(lines))

    def update_checklist(self, attempt: int, step: str, status: str, detail: str = "") -> None:
        elapsed = int(time.time() - getattr(self, "fix_start_time", time.time()))

        lines = [
            "### 🤖 Ella is working on it...\n",
            f"**Limits:** {self.max_attempts} turns | {TIME_LIMIT_SECONDS // 60} minutes",
            f"**Time elapsed:** {elapsed}s",
        ]

        failed = attempt - 1
        if failed > 0:
            lines.append(f"**Progress:** {failed} failed attempt{'s' if failed != 1 else ''} so far.")

        lines.append("")

        lines.append(f"- [{' ' if status == 'working' else 'x'}] Turn {attempt}")
        lines.append("  - [x] Preparing context")
        if step == "calling":
            lines.append(f"  - [{' ' if status == 'working' else 'x'}] Calling AI model")
        elif step == "applying":
            lines.append("  - [x] Calling AI model")
            lines.append(f"  - [{' ' if status == 'working' else 'x'}] Applying changes")
        elif step == "checking":
            lines.append("  - [x] Calling AI model")
            lines.append("  - [x] Applying changes")
            lines.append(f"  - [{' ' if status == 'working' else 'x'}] Running project checks")
        elif step == "done":
            lines.append("  - [x] Calling AI model")
            lines.append("  - [x] Applying changes")
            lines.append("  - [x] Running project checks")

        if detail:
            lines.append(f"\n> {detail}")

        self.update_progress("\n".join(lines))

    def load_pr_metadata(self) -> None:
        raw = gh([
            "pr",
            "view",
            str(self.issue_number),
            "--repo",
            self.repo,
            "--json",
            "title,body,author,baseRefName,headRefName,headRefOid,headRepository,headRepositoryOwner,isCrossRepository,isDraft,state,url,comments",
        ])
        self.pr_info = json.loads(raw)
        write_debug("pr-info.json", json.dumps(self.pr_info, indent=2))

        diff = gh(["pr", "diff", str(self.issue_number), "--repo", self.repo])
        write_debug("pr-diff.txt", diff)
        write_debug("pr-diff-limited.txt", diff[:MAX_CONTEXT_PR_DIFF_BYTES])

    def load_issue_metadata(self) -> None:
        raw = gh([
            "issue",
            "view",
            str(self.issue_number),
            "--repo",
            self.repo,
            "--json",
            "title,body,author,url,number,state,comments",
        ])
        self.issue_info = json.loads(raw)
        write_debug("issue-info.json", json.dumps(self.issue_info, indent=2))

    def checkout_pr_branch(self) -> None:
        if not self.pr_info:
            raise RuntimeError("PR info not loaded")

        head_ref = self.pr_info["headRefName"]
        git(["fetch", "origin",
            f"refs/heads/{head_ref}:refs/remotes/origin/{head_ref}"])
        git(["checkout", "-B", head_ref, f"origin/{head_ref}"])

    def checkout_solve_branch(self) -> None:
        if not self.issue_info:
            raise RuntimeError("Issue info not loaded")

        title = str(self.issue_info.get("title", "issue"))
        safe_title = re.sub(r"[^a-z0-9]+", "-",
                            title.lower()).strip("-")[:50] or "issue"
        branch = f"ella/issue-{self.issue_number}-{safe_title}-{self.run_id}"
        self.solve_branch = branch
        git(["checkout", "-B", branch])

    def get_pr_changed_files(self) -> list[str]:
        raw = gh(["pr", "diff", str(self.issue_number),
                 "--repo", self.repo, "--name-only"])
        files = [line.strip() for line in raw.splitlines() if line.strip()]
        files = [f for f in files if safe_rel_path(
            f) and not is_ignored(f, self.ignore_patterns)]
        write_debug("allowed-files.txt", "\n".join(files) + "\n")
        return files

    def get_repo_files(self) -> list[str]:
        raw = git(["ls-files"])
        files = [line.strip() for line in raw.splitlines() if line.strip()]
        files = [f for f in files if safe_rel_path(
            f) and not is_ignored(f, self.ignore_patterns)]
        write_debug("allowed-files.txt", "\n".join(files) + "\n")
        write_debug("repo-files-limited.txt", ("\n".join(files) +
                    "\n")[:MAX_CONTEXT_REPO_FILES_BYTES])
        return files

    def load_repo_instructions(self) -> None:
        chunks: list[str] = []
        
        core_path = AGENT_DIR / "instructions.md"
        if core_path.exists():
            chunks.append(
                f"\n----- INSTRUCTIONS: Core Agent Instructions -----\n{read_text_limited(core_path, 40_000)}\n----- END INSTRUCTIONS: Core Agent Instructions -----\n")

        for rel in [
            "AGENTS.md",
            "ELLA.md",
            ".github/copilot-instructions.md",
            ".github/ella-instructions.md",
        ]:
            path = ROOT / rel
            if path.exists():
                chunks.append(
                    f"\n----- INSTRUCTIONS: {rel} -----\n{read_text_limited(path, 40_000)}\n----- END INSTRUCTIONS: {rel} -----\n")
        text = "\n".join(chunks)
        write_debug("repo-instructions.txt", text)
        self.repo_instructions = text

    def handle_read_only(self) -> str:
        context = self.build_read_only_context()
        system = self.system_prompt_for_read_only()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": context}
        ]
        content, _ = self.ai_call(messages, MAX_TOKENS[self.mode], use_small=self.mode != "review")
        response = content or ""
        write_debug("ai-response-raw.txt", response)
        response = _strip_tool_call_json(response)
        write_debug("ai-response.txt", response)
        return response

    def build_read_only_context(self) -> str:
        lines = [
            "User request:",
            self.prompt,
            "",
            f"Mode: {self.mode}",
        ]

        if self.mode == "label":
            labels = load_labels()
            lines.extend([
                "",
                "Allowed labels:",
                *[f"- {label['name']}" for label in labels],
                "",
                "Return ONLY valid JSON with this schema:",
                '{ "summary": "short reason", "labels": ["bug", "frontend"] }',
            ])

        if self.pr_info:
            pr_data = dict(self.pr_info)
            comments = pr_data.pop("comments", [])
            lines.extend([
                "",
                "PR info:",
                json.dumps(pr_data, indent=2),
                "",
                "PR diff, possibly truncated:",
                read_pr_diff_limited(),
            ])
            if comments:
                lines.append("\nConversation History (Comments):")
                for c in comments:
                    author = c.get("author", {}).get("login", "unknown")
                    lines.append(f"\n--- Comment by @{author} ---\n{c.get('body', '').strip()}\n-----------------------------")

        if self.issue_info:
            issue_data = dict(self.issue_info)
            comments = issue_data.pop("comments", [])
            lines.extend([
                "",
                "Issue info:",
                json.dumps(issue_data, indent=2),
            ])
            if comments:
                lines.append("\nConversation History (Comments):")
                for c in comments:
                    author = c.get("author", {}).get("login", "unknown")
                    lines.append(f"\n--- Comment by @{author} ---\n{c.get('body', '').strip()}\n-----------------------------")

        context = "\n".join(lines)
        write_debug("context.txt", context)
        return context

    def system_prompt_for_read_only(self) -> str:
        base = "You are Ella Mizuki, a charismatic female AI assistant. The repository owner is Yuri (the developer who set you up). You are not Yuri - you are Ella. Write in English with a warm, charismatic tone. Use first-person ('I')."
        if self.mode == "review":
            return base + ' Do a thorough code review. Find bugs, security risks, type issues, and suspicious code. Return ONLY valid JSON: { "summary": "review summary in Markdown", "comments": [ { "path": "src/file.py", "line": 42, "body": "comment" } ] }. Only reference lines that exist in the diff. No markdown fences.'
        if self.mode == "plan":
            return base + " Write a clear, practical implementation plan. Include likely files, steps, risks, and checks."
        if self.mode == "label":
            return base + ' Classify this issue or PR with the most relevant labels. Return ONLY valid JSON: { "labels": ["bug"], "summary": "one short sentence explaining the choice" }. No markdown fences. The summary must be a single brief sentence.'
        if self.mode == "pr":
            return base + " Give a short, friendly PR analysis: what changed, risks, and merge readiness."
        return base + " Be friendly and concise. Answer in plain text. No JSON or tool-call syntax."

    def handle_label(self) -> None:
        response = self.handle_read_only()
        labels_config = load_labels()
        labels_by_name = {x["name"].lower(): x for x in labels_config}

        try:
            data = parse_jsonish(response)
        except Exception:
            self.comment("I could not parse the label response as JSON.")
            self.react("confused")
            return

        picked: list[str] = []
        for item in data.get("labels", []):
            if not isinstance(item, str):
                continue
            name = item.strip().lower()
            if name in labels_by_name and name not in picked:
                picked.append(name)

        if not picked:
            self.comment("I could not find any valid labels to apply.")
            self.react("confused")
            return

        for item in labels_config:
            gh([
                "label",
                "create",
                item["name"],
                "--repo",
                self.repo,
                "--color",
                item.get("color", "ededed"),
                "--description",
                item.get("description", ""),
            ], check=False)

        for name in picked:
            gh(["issue", "edit", str(self.issue_number), "--repo",
               self.repo, "--add-label", labels_by_name[name]["name"]])

        summary = str(data.get("summary")
                      or "I applied the most relevant labels.").strip()
        write_debug("labels.txt", "\n".join(picked) + "\n")
        write_debug("label-summary.txt", summary + "\n")
        self.comment(
            f"I applied these labels: {', '.join(labels_by_name[name]['name'] for name in picked)}\n\n{summary}")

    def post_inline_review(self, summary: str, comments: list[dict]) -> None:
        if not self.pr_info:
            return
        commit_id = self.pr_info.get("headRefOid")
        if not commit_id:
            return
            
        payload = {
            "commit_id": commit_id,
            "event": "COMMENT",
            "body": scrub_secrets(summary) or "Ella's Code Review",
            "comments": []
        }

        for c in comments:
            path = c.get("path")
            line = c.get("line")
            body = c.get("body")
            if path and line and body:
                payload["comments"].append({
                    "path": str(path),
                    "line": int(line),
                    "side": "RIGHT",
                    "body": scrub_secrets(str(body))
                })

        if not payload["comments"]:
            self.comment(summary)
            return

        json_payload = json.dumps(payload)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            f.write(json_payload)
            temp_path = f.name

        try:
            gh(["api", "--method", "POST", f"repos/{self.repo}/pulls/{self.issue_number}/reviews", "--input", temp_path])
            self.comment("I left a few inline comments on the changed files! 🚀")
        except Exception as e:
            print(f"Failed to post inline review: {e}")
            self.comment(summary + "\n\n(Note: I tried to post inline comments but an error occurred.)")
        finally:
            os.remove(temp_path)


    def handle_heal(self) -> None:
        run_data = self.event.get("workflow_run", {})
        run_id = run_data.get("id")
        head_branch = run_data.get("head_branch")
        
        if not run_id:
            print("No run_id found in workflow_run event")
            return
            
        pull_requests = run_data.get("pull_requests", [])
        if pull_requests:
            self.issue_number = pull_requests[0].get("number")
        else:
            try:
                pr_list = json.loads(gh(["pr", "list", "--head", head_branch, "--repo", self.repo, "--json", "number"]))
                if pr_list:
                    self.issue_number = pr_list[0]["number"]
            except Exception as e:
                print(f"Failed to find PR for branch {head_branch}: {e}")
                
        if not self.issue_number:
            print("No PR found to heal.")
            return
            
        self.is_pr = True
        self.load_pr_metadata()
        
        author = self.pr_info.get("author", {}).get("login", "")
        
        # Download failed logs
        try:
            failed_logs = gh(["run", "view", str(run_id), "--log-failed", "--repo", self.repo])
        except Exception as e:
            print(f"Failed to get logs for run {run_id}: {e}")
            failed_logs = "Logs unavailable."

        # Keep logs limited
        if len(failed_logs) > 8000:
            failed_logs = "...(truncated)...\n" + failed_logs[-8000:]
        failed_logs = scrub_secrets(failed_logs)
            
        if "dependabot" in author.lower():
            self.prompt = f"Dependabot updated a dependency and broke CI. Check the logs, find the migration guide if needed, and fix the breaking changes.\n\nLogs:\n{failed_logs}"
        else:
            self.prompt = f"CI failed on this PR. Analyze the logs and fix the issue.\n\nLogs:\n{failed_logs}"
            
        self.checkout_pr_branch()
        self.load_repo_instructions()
        self.allowed_files = self.get_pr_changed_files()
        
        # Adding common files for context in heal mode
        for common in ["package.json", "pyproject.toml", "go.mod", "Cargo.toml"]:
            if (ROOT / common).exists() and common not in self.allowed_files:
                self.allowed_files.append(common)
                
        self.create_progress_comment(
            self.generate_message(
                "I detected a CI failure on a PR and I'm on it. Write 1-2 friendly sentences saying I'm investigating. No headers.",
                fallback="I detected a CI failure and I'm automatically trying to fix it!"
            )
            + f"\n\n**Limits:** {self.max_attempts} turns | {TIME_LIMIT_SECONDS // 60} minutes"
        )
        
        success = self.fix_loop()
        if success:
            commit_sha = self.commit_and_push_fix()
            if commit_sha:
                msg = self.generate_message(
                    f"I auto-healed the CI (commit {commit_sha}). Summary: {self.final_summary}. Write 2-3 friendly sentences referencing the commit. No headers.",
                    fallback=f"🚑 I successfully auto-healed the CI pipeline!\n\nCommit: `{commit_sha}`\n\n{self.final_summary}"
                )
                self.comment(msg)
            else:
                msg = self.generate_message(
                    f"All checks passed, no code changes needed. Summary: {self.final_summary}. Write 2-3 friendly sentences. No headers.",
                    fallback=f"🚑 All checks passed and no changes were needed.\n\n{self.final_summary}"
                )
                self.comment(msg)
            self.react("rocket")
        else:
            msg = self.generate_message(
                f"I tried to auto-heal the CI but couldn't get checks to pass. Summary: {self.final_summary}. Write 2-3 friendly sentences explaining the failure. No headers.",
                fallback=f"🚑 I tried to auto-heal the CI but couldn't pass all checks within the limits.\n\n{self.final_summary}"
            )
            self.comment(msg)
            self.react("confused")

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "Search the codebase using git grep.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search term"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filepath": {"type": "string", "description": "Path to the file, relative to repo root."}
                        },
                        "required": ["filepath"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "description": "Edit a file by finding a unique block of text and replacing it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filepath": {"type": "string", "description": "Path to the file, relative to repo root."},
                            "search_text": {"type": "string", "description": "Exact text to replace. Must be unique in the file."},
                            "replace_text": {"type": "string", "description": "The new text"}
                        },
                        "required": ["filepath", "search_text", "replace_text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_tests",
                    "description": "Run the project checks (auto-detected lint, typecheck, test, and build commands).",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "done",
                    "description": "Signal that the task is complete and provide a summary of what was done.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"}
                        },
                        "required": ["summary"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "think",
                    "description": "Use this tool to plan your next steps, write down your reasoning, or diagnose an error. This does not execute any code but helps you organize your thoughts before making changes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "thought": {"type": "string", "description": "Your detailed reasoning or plan."}
                        },
                        "required": ["thought"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_terminal_command",
                    "description": "Run a terminal command (linter, type checker, ls, git status, etc.) to inspect or validate the code state. Destructive commands (rm -rf, git push, git reset --hard, git checkout ., git clean, force push, dropping databases, mkfs, etc.) are blocked.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The bash command to execute."},
                            "cwd": {"type": "string", "description": "Optional subdirectory to run the command in (relative to repo root, e.g. 'packages/ui'). Defaults to repo root."}
                        },
                        "required": ["command"]
                    }
                }
            }
        ]

    def ai_call(self, messages: list[dict], max_tokens: int, tools: list[dict] | None = None, use_small: bool = False) -> tuple[str, list[dict]]:
        model = self.ai_small_model if use_small else self.ai_model
        base_url = self.ai_small_base_url if use_small else self.ai_base_url
        api_key = self.ai_small_api_key if use_small else self.ai_api_key

        body = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        data = json.dumps(body).encode("utf-8")
        url = base_url.rstrip("/") + "/chat/completions"

        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Cache-Control": "no-cache",
                "User-Agent": "curl/8.7.1",
            },
        )

        content_parts: list[str] = []
        active_tool_calls: dict[str, dict] = {}
        index_to_id: dict[int, str] = {}

        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                status = getattr(response, "status", 200)
                print(f"HTTP status: {status}")

                for raw in response:
                    line = raw.decode("utf-8", errors="replace")
                    stripped = line.strip()
                    if not stripped or stripped.startswith(":"):
                        continue

                    if stripped.startswith("data:"):
                        payload = stripped[len("data:"):].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        try:
                            self.collect_ai_choices(obj, content_parts, active_tool_calls, index_to_id)
                        except Exception as e:
                            print(f"Skipping malformed SSE chunk: {e}")
                    else:
                        try:
                            obj = json.loads(stripped)
                        except json.JSONDecodeError:
                            continue
                        try:
                            self.collect_ai_choices(obj, content_parts, active_tool_calls, index_to_id)
                        except Exception as e:
                            print(f"Skipping malformed chunk: {e}")

        except urllib.error.HTTPError as exc:
            raise CommandError(scrub_secrets(f"AI endpoint failed with HTTP status {exc.code}."))
        except urllib.error.URLError as exc:
            raise CommandError(scrub_secrets(f"AI endpoint request failed: {exc.reason}"))

        content = "".join(content_parts).strip()
        tool_calls = list(active_tool_calls.values())
        return content, tool_calls

    @staticmethod
    def collect_ai_choices(obj: dict, content_parts: list[str], active_tool_calls: dict, index_to_id: dict) -> None:
        if not isinstance(obj, dict):
            return

        for choice in obj.get("choices") or []:
            if not isinstance(choice, dict):
                continue

            delta = choice.get("delta") or {}
            message = choice.get("message") or {}

            content = delta.get("content") or message.get("content") or choice.get("text")
            if content:
                content_parts.append(str(content))

            tcs = delta.get("tool_calls") or message.get("tool_calls") or choice.get("tool_calls") or []
            for tc in tcs:
                idx = tc.get("index", 0)
                tc_id = tc.get("id")
                
                if tc_id:
                    index_to_id[idx] = tc_id
                    if tc_id not in active_tool_calls:
                        active_tool_calls[tc_id] = {
                            "id": tc_id,
                            "type": tc.get("type", "function"),
                            "function": {"name": tc.get("function", {}).get("name"), "arguments": ""}
                        }
                
                current_id = index_to_id.get(idx)
                if not current_id:
                    current_id = f"call_{idx}"
                    index_to_id[idx] = current_id
                    active_tool_calls[current_id] = {
                        "id": current_id,
                        "type": "function",
                        "function": {"name": "", "arguments": ""}
                    }
                
                fn = tc.get("function", {})
                args = fn.get("arguments", "")
                if args:
                    active_tool_calls[current_id]["function"]["arguments"] += args

    def execute_tool(self, name: str, arguments: str) -> str:
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return "Error: arguments must be valid JSON."

        if name == "search_code":
            query = args.get("query", "")
            if not query:
                return "Error: query is required."
            res = run_cmd(["git", "grep", "-n", query], capture=True, check=False)
            if res.returncode == 0:
                return res.stdout or "No results found."
            return "No results found or error executing search."
            
        elif name == "read_file":
            filepath = args.get("filepath", "")
            path = ROOT / filepath
            try:
                if not path.resolve().is_relative_to(ROOT_RESOLVED):
                    return f"Error: unauthorized path {filepath}. Access outside repository is denied."
            except ValueError:
                return f"Error: invalid path {filepath}."
            if not path.exists():
                return f"Error: file {filepath} not found."
            return f"--- {filepath} ---\n" + read_text_limited(path, MAX_CONTEXT_FILE_BYTES)
            
        elif name == "edit_file":
            filepath = args.get("filepath", "")
            search_text = args.get("search_text", "")
            replace_text = args.get("replace_text", "")
            path = ROOT / filepath
            
            try:
                if not path.resolve().is_relative_to(ROOT_RESOLVED):
                    return f"Error: unauthorized path {filepath}. Access outside repository is denied."
            except ValueError:
                return f"Error: invalid path {filepath}."
            
            if not path.exists():
                return f"Error: file {filepath} not found."
            
            text = path.read_text(encoding="utf-8", errors="replace")
            if search_text not in text:
                return "Error: search_text not found in file. Make sure you provided the exact text including whitespace."
            if text.count(search_text) > 1:
                return "Error: search_text is not unique. Provide a larger block of text."
                
            new_text = text.replace(search_text, replace_text)
            path.write_text(new_text, encoding="utf-8")
            return f"Successfully edited {filepath}."
            
        elif name == "run_tests":
            self.run_project_checks()
            checks_summary = read_checks_summary()
            return checks_summary or "Checks ran but no output was captured."
            
        elif name == "done":
            summary = args.get("summary", "")
            if summary:
                write_debug("fix-summary.txt", str(summary).strip())
            return "Task completed."
            
        elif name == "think":
            return "Thought recorded. You can now execute the next tool based on this plan."
            
        elif name == "run_terminal_command":
            cmd = args.get("command", "")
            if not cmd:
                return "Error: command is required."

            blocked_patterns = [
                r"\brm\s+-rf\b", r"\brm\s+-fr\b", r"\brm\s+-r\b",
                r"\bgit\s+push\b", r"\bgit\s+reset\s+--hard\b",
                r"\bgit\s+checkout\s+\.\s*$", r"\bgit\s+clean\s+-fd\b",
                r"\bDROP\s+(?:TABLE|DATABASE)\b", r"\bTRUNCATE\b",
                r"\bmkfs\b", r"\bdd\s+.*of=/dev/", r"\b:\(\)\s*\{",
            ]
            for pattern in blocked_patterns:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return f"Error: this command is blocked for safety: {cmd}"

            cwd_override = ROOT
            cwd_arg = args.get("cwd", "")
            if cwd_arg:
                cwd_path = (ROOT / cwd_arg).resolve()
                try:
                    if not cwd_path.is_relative_to(ROOT_RESOLVED):
                        return f"Error: cwd must be inside the repository. Got: {cwd_arg}"
                except ValueError:
                    return f"Error: invalid cwd path: {cwd_arg}"
                if not cwd_path.is_dir():
                    return f"Error: directory not found: {cwd_arg}"
                cwd_override = cwd_path

            res = run_cmd(["bash", "-lc", cmd], capture=True, check=False, cwd=cwd_override)
            output = scrub_secrets(res.stdout or "")
            if len(output) > 8000:
                output = "...(truncated)\n" + output[-8000:]
            return f"Exit code: {res.returncode}\n\nOutput:\n{output}" if output else f"Exit code: {res.returncode} (no output)"
            
        return f"Error: Unknown tool {name}."

    def compute_max_attempts(self) -> int:
        max_attempts = env_int("ELLA_MAX_ATTEMPTS", 25 + 2 * len(self.allowed_files))
        return min(max_attempts, 300)

    @staticmethod
    def _bump_consecutive_error(consecutive: int, attempt: int) -> tuple[int, int]:
        consecutive += 1
        if consecutive >= 3:
            attempt += 1
            consecutive = 0
        return consecutive, attempt

    def fix_loop(self) -> bool:
        start = time.time()
        self.fix_start_time = start
        self.max_attempts = self.compute_max_attempts()

        if not self.prepare_environment():
            self.final_summary = "Failure type: install_failed\n\nInstall failed before I could safely edit.\n\n" + (OUT / "install-summary.md").read_text(encoding="utf-8", errors="replace")
            write_debug("final-summary.md", self.final_summary)
            self.update_progress("❌ I stopped before editing.\n\nReason: install failed.\nA debug artifact will be uploaded if available.")
            return False

        system = self.system_prompt_for_fix()
        context = self.build_fix_context(1)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": context}
        ]
        
        attempt = 1
        consecutive_errors = 0
        
        while attempt <= self.max_attempts:
            elapsed = int(time.time() - start)
            if elapsed >= TIME_LIMIT_SECONDS:
                self.final_summary = f"Failure type: time_limit\n\nTime limit reached before I could finish the task.\n\nTurns used: {attempt}/{self.max_attempts}\nTime used: {elapsed}s/{TIME_LIMIT_SECONDS}s"
                try:
                    wip_sha = self.commit_and_push_wip(f"time limit reached after {elapsed}s")
                    if wip_sha:
                        self.final_summary += f"\n\nPushed WIP commit `{wip_sha}` with partial progress."
                except Exception as e:
                    print(f"Failed to push WIP commit: {e}")
                
                write_debug("final-summary.md", self.final_summary)
                self.update_progress(f"⏱️ I reached the time limit. {('WIP commit pushed.' if 'wip_sha' in locals() and wip_sha else '')}\n\nTurns: {attempt}/{self.max_attempts}\nTime used: {elapsed}s/{TIME_LIMIT_SECONDS}s")
                return False

            self.update_checklist(attempt, "calling", "working")

            try:
                content, tool_calls = self.ai_call(messages, MAX_TOKENS.get(self.mode, 16384), tools=self.get_tools())
            except Exception as exc:
                self.feedback = f"Failure type: ai_endpoint\n\n{exc}"
                write_debug("feedback.txt", self.feedback)
                consecutive_errors, attempt = self._bump_consecutive_error(consecutive_errors, attempt)
                continue

            if content:
                write_debug(f"ai-response-{attempt}.txt", content)

            if not tool_calls:
                if content:
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "You didn't call any tools! You MUST call a tool. If you need to make changes, use `edit_file`. If you are finished, you MUST call the `done` tool. DO NOT echo tool outputs or return plain text."})
                self.update_checklist(attempt, "applying", "failed", "No tools called")
                consecutive_errors, attempt = self._bump_consecutive_error(consecutive_errors, attempt)
                continue
            
            # Reset consecutive errors since we successfully got tool calls
            consecutive_errors = 0

            tool_call_messages = []
            done_called = False
            for tc in tool_calls:
                name = tc.get("function", {}).get("name", "")
                args = tc.get("function", {}).get("arguments", "")
                
                if name == "done":
                    done_called = True
                
                self.update_checklist(attempt, "applying", "working", f"Running tool {name}")
                result = self.execute_tool(name, args)
                tool_call_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "name": name,
                    "content": result
                })
            
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls
            })
            messages.extend(tool_call_messages)
            
            if done_called:
                self.update_checklist(attempt, "checking", "working")
                if self.run_project_checks():
                    self.final_summary = "I applied the fix successfully.\n\n" + read_checks_summary()
                    write_debug("final-summary.md", self.final_summary)
                    self.update_checklist(attempt, "done", "success", "Checks passed! Committing changes.")
                    return True
                else:
                    self.update_checklist(attempt, "checking", "failed", "Project checks failed. Will retry.")
                    messages.append({"role": "user", "content": "The project checks failed. Please review the errors and fix them:\n" + read_checks_summary()})
                    attempt += 1
                    continue
            
            attempt += 1

        self.final_summary = f"I reached the maximum limit of {self.max_attempts} turns before I could finish the task.\n\nTurns used: {self.max_attempts}/{self.max_attempts}\nStatus: stopped without committing.\n\n" + read_checks_summary()
        try:
            wip_sha = self.commit_and_push_wip("turn limit reached")
            if wip_sha:
                self.final_summary += f"\n\nPushed WIP commit `{wip_sha}` with partial progress."
        except Exception as e:
            print(f"Failed to push WIP commit: {e}")
            
        write_debug("final-summary.md", self.final_summary)
        self.update_progress(f"❌ I reached the turn limit ({self.max_attempts}/{self.max_attempts}). {('WIP commit pushed.' if 'wip_sha' in locals() and wip_sha else '')}")
        return False

    def system_prompt_for_fix(self) -> str:
        if self.mode == "solve":
            action = "You're solving a GitHub issue by editing a branch and opening a PR."
        else:
            action = "You're fixing an existing PR."
        return (
            "You are Ella Mizuki, a charismatic female AI assistant. The repository owner is Yuri (the developer who set you up). You are not Yuri - you are Ella. "
            "Write in English with a warm, charismatic tone. Use first-person ('I'). "
            f"{action} Use the provided tools to inspect and modify the repository.\n\n"
            "RULES:\n"
            "1. Never echo tool outputs.\n"
            "2. Need more work? Call the next tool immediately.\n"
            "3. Tool failed? Use `think` to diagnose before retrying.\n"
            "4. Finished? Call the `done` tool.\n"
            "5. Never output plain text without a tool call."
        )

    def build_fix_context(self, attempt: int) -> str:
        lines: list[str] = [
            f"You are running attempt {attempt} of {self.max_attempts}.",
            f"Time limit: {TIME_LIMIT_SECONDS} seconds.",
            "",
            "User request:",
            self.prompt,
            "",
            "Repository instructions:",
            getattr(self, "repo_instructions", ""),
            "",
            "Tool calling:",
            "Tools: search_code, read_file, edit_file, run_tests, run_terminal_command, think, done.",
            "Always use tool calls. No plain text responses.",
            "",
            "Rules:",
            "- English, first-person, friendly tone.",
            "- edit_file for all file changes.",
            "- Smallest safe change possible.",
            "- No editing secrets, env files, lockfiles, or generated files.",
            "- Fix only the feedback from previous attempts.",
            "",
            "Previous failure type and feedback:",
            self.feedback,
            "",
            "Extra file context requested in previous attempts:",
            self.extra_context,
            "",
            "Allowed files:",
            "\n".join(self.allowed_files),
        ]

        if self.mode in {"fix", "continue"}:
            pr_data = dict(self.pr_info or {})
            comments = pr_data.pop("comments", [])
            lines.extend([
                "",
                "PR info:",
                json.dumps(pr_data, indent=2),
                "",
                "PR diff, truncated:",
                read_pr_diff_limited(),
                "",
                "Allowed files current content, truncated:",
            ])
            for rel in self.allowed_files:
                path = ROOT / rel
                if path.exists():
                    lines.append(
                        f"\n----- FILE: {rel} -----\n{read_text_limited(path, MAX_CONTEXT_FILE_BYTES)}\n----- END FILE: {rel} -----")
            if comments:
                lines.append("\nConversation History (Comments):")
                for c in comments:
                    author = c.get("author", {}).get("login", "unknown")
                    lines.append(f"\n--- Comment by @{author} ---\n{c.get('body', '').strip()}\n-----------------------------")

        if self.mode == "solve":
            issue_data = dict(self.issue_info or {})
            comments = issue_data.pop("comments", [])
            lines.extend([
                "",
                "Issue info:",
                json.dumps(issue_data, indent=2),
                "",
                "Repository files, truncated:",
                (OUT / "repo-files-limited.txt").read_text(encoding="utf-8",
                                                           errors="replace") if (OUT / "repo-files-limited.txt").exists() else "",
                "",
                "Common project files:",
            ])
            for rel in [
                "package.json",
                "turbo.json",
                "pnpm-workspace.yaml",
                "pyproject.toml",
                "requirements.txt",
                "go.mod",
                "Cargo.toml",
                "Dockerfile",
                "docker-compose.yml",
                "compose.yml",
                "README.md",
                "tsconfig.json",
            ]:
                path = ROOT / rel
                if path.exists() and not is_ignored(rel, self.ignore_patterns):
                    lines.append(
                        f"\n----- FILE: {rel} -----\n{read_text_limited(path, MAX_CONTEXT_FILE_BYTES)}\n----- END FILE: {rel} -----")
            if comments:
                lines.append("\nConversation History (Comments):")
                for c in comments:
                    author = c.get("author", {}).get("login", "unknown")
                    lines.append(f"\n--- Comment by @{author} ---\n{c.get('body', '').strip()}\n-----------------------------")

        context = "\n".join(lines)
        write_debug("context.txt", context)
        return context

    def prepare_environment(self) -> bool:
        if (ROOT / ".ella" / "checks.sh").exists():
            write_debug("install-summary.md",
                        "- ⚪ custom .ella/checks.sh found, install is handled by the custom checks script\n")
            return True

        summaries: list[str] = []
        ok = True

        for name, cmd in self.detect_install_commands():
            success, log = self.run_logged_check(
                f"install-{name}", cmd, timeout=1200)
            summaries.append(f"- {'✅' if success else '❌'} install ({name})")
            if not success:
                summaries.append("")
                summaries.append(f"Last lines from install ({name}):")
                summaries.append("```txt")
                summaries.append(log)
                summaries.append("```")
                ok = False

        if not summaries:
            summaries.append("- ⚪ no automatic install command detected")

        write_debug("install-summary.md", "\n".join(summaries) + "\n")
        return ok

    def detect_install_commands(self) -> list[tuple[str, list[str]]]:
        commands: list[tuple[str, list[str]]] = []

        if (ROOT / "package.json").exists():
            if (ROOT / "pnpm-lock.yaml").exists():
                commands.append(
                    ("pnpm", ["bash", "-lc", "corepack enable || true; pnpm install --frozen-lockfile"]))
            elif (ROOT / "package-lock.json").exists():
                commands.append(("npm", ["npm", "ci"]))
            elif (ROOT / "yarn.lock").exists():
                commands.append(
                    ("yarn", ["bash", "-lc", "corepack enable || true; yarn install --frozen-lockfile"]))
            elif (ROOT / "bun.lockb").exists() or (ROOT / "bun.lock").exists():
                if command_exists("bun"):
                    commands.append(
                        ("bun", ["bun", "install", "--frozen-lockfile"]))
            elif command_exists("bun"):
                commands.append(("bun", ["bun", "install"]))

        if (ROOT / "pyproject.toml").exists():
            if (ROOT / "uv.lock").exists() and command_exists("uv"):
                commands.append(("uv", ["uv", "sync"]))
            elif (ROOT / "poetry.lock").exists() and command_exists("poetry"):
                commands.append(
                    ("poetry", ["poetry", "install", "--no-interaction"]))
            elif (ROOT / "requirements.txt").exists():
                commands.append(
                    ("pip", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]))
            elif _pyproject_has_build_target(ROOT / "pyproject.toml"):
                commands.append(
                    ("pip-editable", [sys.executable, "-m", "pip", "install", "-e", "."]))
        elif (ROOT / "requirements.txt").exists():
            commands.append(
                ("pip", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]))

        if (ROOT / "composer.json").exists() and command_exists("composer"):
            commands.append(
                ("composer", ["composer", "install", "--no-interaction", "--no-progress"]))

        return commands

    def run_project_checks(self) -> bool:
        summary: list[str] = ["Checks executed:", ""]
        install_summary = (OUT / "install-summary.md")
        if install_summary.exists():
            summary.append(install_summary.read_text(
                encoding="utf-8", errors="replace").strip())
            summary.append("")

        if (ROOT / ".ella" / "checks.sh").exists():
            checks = [("custom-checks", ["bash", ".ella/checks.sh"])]
        else:
            checks = self.detect_check_commands()

        if not checks:
            summary.append("- ⚪ no automatic checks detected")
            write_debug("checks-summary.md", "\n".join(summary) + "\n")
            return True

        all_ok = True
        for name, cmd in checks:
            success, log_tail = self.run_logged_check(name, cmd, timeout=1500)
            summary.append(f"- {'✅' if success else '❌'} {name}")
            if not success:
                all_ok = False
                summary.append("")
                summary.append(f"Last lines from {name}:")
                summary.append("```txt")
                summary.append(log_tail)
                summary.append("```")

        write_debug("checks-summary.md", "\n".join(summary) + "\n")
        return all_ok

    def detect_check_commands(self) -> list[tuple[str, list[str]]]:
        checks: list[tuple[str, list[str]]] = []

        if (ROOT / "package.json").exists():
            scripts = {}
            try:
                package = json.loads(
                    (ROOT / "package.json").read_text(encoding="utf-8"))
                scripts = package.get("scripts") or {}
            except Exception:
                scripts = {}

            if (ROOT / "pnpm-lock.yaml").exists():
                runner = ["pnpm", "run"]
            elif (ROOT / "yarn.lock").exists():
                runner = ["yarn"]
            elif (ROOT / "bun.lockb").exists() or (ROOT / "bun.lock").exists():
                runner = ["bun", "run"] if command_exists("bun") else [
                    "npm", "run"]
            else:
                runner = ["npm", "run"]

            for script in ["lint", "typecheck", "test", "build"]:
                if script in scripts:
                    checks.append((f"node-{script}", [*runner, script]))

        # Stacks with a single marker file + required command.
        simple_stacks: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
            ("go.mod", "go", [
                ("go-fmt", ["bash", "-lc", 'test -z "$(gofmt -l .)"']),
                ("go-vet", ["go", "vet", "./..."]),
                ("go-test", ["go", "test", "./..."]),
            ]),
            ("Cargo.toml", "cargo", [
                ("cargo-fmt", ["cargo", "fmt", "--check"]),
                ("cargo-clippy", ["cargo", "clippy", "--", "-D", "warnings"]),
                ("cargo-test", ["cargo", "test"]),
            ]),
            ("pom.xml", "mvn", [
                ("maven-test", ["mvn", "test"]),
            ]),
        ]
        for marker, cmd, stack_checks in simple_stacks:
            if (ROOT / marker).exists() and command_exists(cmd):
                checks.extend(stack_checks)

        # .NET: marker is a glob, not a single file.
        if (any(ROOT.glob("*.sln")) or any(ROOT.glob("**/*.csproj"))) and command_exists("dotnet"):
            checks.append(("dotnet-restore", ["dotnet", "restore"]))
            checks.append(("dotnet-build", ["dotnet", "build", "--no-restore"]))
            checks.append(("dotnet-test", ["dotnet", "test", "--no-build"]))

        # Gradle: requires both a build file and the wrapper script.
        if ((ROOT / "build.gradle").exists() or (ROOT / "build.gradle.kts").exists()) and (ROOT / "gradlew").exists():
            checks.append(("gradle-test", ["./gradlew", "test"]))

        if (ROOT / "test.py").exists():
            checks.append(("test.py", [sys.executable, "test.py"]))

        if (ROOT / "pyproject.toml").exists() or (ROOT / "requirements.txt").exists() or (ROOT / "pytest.ini").exists():
            if self.python_module_exists("ruff") or command_exists("ruff"):
                cmd = ["ruff", "check", "."] if command_exists(
                    "ruff") else [sys.executable, "-m", "ruff", "check", "."]
                checks.append(("python-ruff", cmd))
            if self.python_module_exists("black") or command_exists("black"):
                cmd = ["black", "--check", "."] if command_exists(
                    "black") else [sys.executable, "-m", "black", "--check", "."]
                checks.append(("python-black", cmd))
            if self.python_module_exists("mypy") or command_exists("mypy"):
                cmd = ["mypy", "."] if command_exists(
                    "mypy") else [sys.executable, "-m", "mypy", "."]
                checks.append(("python-mypy", cmd))
            if self.python_module_exists("pytest") or command_exists("pytest"):
                cmd = ["pytest"] if command_exists("pytest") else [
                    sys.executable, "-m", "pytest"]
                checks.append(("python-pytest", cmd))

        if (ROOT / "composer.json").exists():
            if (ROOT / "vendor/bin/phpunit").exists():
                checks.append(("phpunit", ["vendor/bin/phpunit"]))
            if (ROOT / "vendor/bin/phpstan").exists():
                checks.append(("phpstan", ["vendor/bin/phpstan", "analyse"]))

        if (ROOT / "docker-compose.yml").exists() or (ROOT / "compose.yml").exists():
            if command_exists("docker"):
                compose_file = "docker-compose.yml" if (
                    ROOT / "docker-compose.yml").exists() else "compose.yml"
                checks.append(
                    ("docker-compose-config", ["docker", "compose", "-f", compose_file, "config"]))

        return checks

    def python_module_exists(self, module: str) -> bool:
        result = run_cmd(
            [sys.executable, "-c", f"import {module}"], check=False, capture=True, timeout=30, env=clean_env_for_checks())
        return result.returncode == 0

    def run_logged_check(self, name: str, cmd: list[str], timeout: int = 900, cwd: Path | None = None) -> tuple[bool, str]:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name)
        log_path = OUT / f"check-{safe_name}.log"
        print(f"Running {name}...")

        try:
            result = subprocess.run(
                cmd,
                cwd=ROOT if cwd is None else cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                env=clean_env_for_checks(),
            )
            log_path.write_text(scrub_secrets(result.stdout or ""),
                                encoding="utf-8", errors="replace")
            return result.returncode == 0, tail_text(log_path, 120)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            output += f"\nCommand timed out after {timeout}s.\n"
            log_path.write_text(scrub_secrets(output), encoding="utf-8", errors="replace")
            return False, tail_text(log_path, 120)
        except Exception as exc:
            log_path.write_text(scrub_secrets(str(exc)), encoding="utf-8", errors="replace")
            return False, scrub_secrets(str(exc))

    def infer_commit_type(self, changed_files: list[str]) -> tuple[str, str | None]:
        normalized = [path.replace("\\", "/") for path in changed_files]

        if not normalized:
            return "chore", None

        if all(
            path.endswith((".md", ".mdx", ".txt", ".rst"))
            or path.lower().endswith("readme")
            or "/docs/" in path
            or path.startswith("docs/")
            for path in normalized
        ):
            return "docs", None

        if all(
            path.startswith(".github/workflows/")
            or path.startswith(".github/actions/")
            or path.startswith(".ella/")
            or path in {"Dockerfile", "docker-compose.yml", "compose.yml"}
            or path.endswith((".yml", ".yaml"))
            for path in normalized
        ):
            return "ci", None

        if all(
            "/test/" in path
            or "/tests/" in path
            or path.startswith("test/")
            or path.startswith("tests/")
            or path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".test.js", ".spec.js"))
            for path in normalized
        ):
            return "test", None

        if any(
            path.endswith(("package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb"))
            or "dependabot" in path
            for path in normalized
        ):
            return "chore", "deps"

        if any(
            path.startswith("apps/web/")
            or path.startswith("apps/docs/")
            or path.startswith("packages/ui/")
            for path in normalized
        ):
            return "fix", "ui"

        return "fix", None

    def fallback_commit_message(self, changed_files: list[str]) -> str:
        commit_type, scope = self.infer_commit_type(changed_files)
        summary = "apply requested changes"

        raw_summary = ""
        summary_path = OUT / "fix-summary.txt"
        if summary_path.exists():
            raw_summary = summary_path.read_text(encoding="utf-8", errors="replace").strip()

        if raw_summary:
            first_line = raw_summary.splitlines()[0].strip()
            first_line = re.sub(r"^(fix|fixed|change|changed|update|updated|add|added):?\s+", "", first_line, flags=re.I)
            if first_line:
                summary = first_line[:90].rstrip(" .")

        if self.mode == "solve":
            issue_title = ""
            if self.issue_info:
                issue_title = str(self.issue_info.get("title", "")).strip()
            if issue_title:
                summary = issue_title[:90].rstrip(" .")

        subject_prefix = f"{commit_type}({scope})" if scope else commit_type
        subject = f"{subject_prefix}: {summary}"
        if len(subject) > 72:
            subject = subject[:69].rstrip(" .") + "..."

        body_lines = [
            "Details:",
            f"- Request: {self.prompt}",
        ]

        if raw_summary:
            body_lines.append(f"- Summary: {raw_summary}")

        if changed_files:
            body_lines.append("- Changed files:")
            for path in changed_files[:12]:
                body_lines.append(f"  - {path}")
            if len(changed_files) > 12:
                body_lines.append(f"  - ...and {len(changed_files) - 12} more")

        if self.mode == "solve":
            body_lines.append(f"- Refs: #{self.issue_number}")

        return subject + "\n\n" + "\n".join(body_lines).strip() + "\n"

    def generate_commit_message(self, changed_files: list[str]) -> str:
        fallback = self.fallback_commit_message(changed_files)

        diff_stat = git(["diff", "--stat"], check=False)
        diff = git(["diff", "--", *changed_files], check=False) if changed_files else ""
        diff = diff[:12000]

        summary = ""
        summary_path = OUT / "fix-summary.txt"
        if summary_path.exists():
            summary = summary_path.read_text(encoding="utf-8", errors="replace").strip()

        context_lines = [
            "Write a Conventional Commit message for these changes.",
            "",
            "Rules:",
            "- Return ONLY valid JSON. No markdown, no code fences.",
            "- Subject: Conventional Commits format (e.g., docs: update README, fix(ui): handle empty state).",
            "- Subject max 72 characters, imperative mood.",
            "- Body: 2-6 concise bullet points.",
            "- English. Don't mention Ella unless the changes are about Ella.",
            "",
            f"Mode: {self.mode}",
            f"Issue/PR number: {self.issue_number}",
            "",
            "User request:",
            self.prompt,
            "",
            "AI change summary:",
            summary,
            "",
            "Changed files:",
            "\n".join(changed_files),
            "",
            "Diff stat:",
            diff_stat,
            "",
            "Diff (truncated):",
            diff,
            "",
            "Schema:",
            '{ "subject": "type(scope): short summary", "body": "- Detail one\\n- Detail two" }',
        ]

        system_prompt = (
            "Write high-quality git commit messages. "
            "Return only valid JSON with subject and body. "
            "No tools, no reasoning."
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(context_lines)},
            ]
            response, _ = self.ai_call(messages, 1200)
            data = parse_jsonish(response)

            subject = str(data.get("subject", "")).strip()
            body = str(data.get("body", "")).strip()

            if self.yuri_name and self.yuri_email:
                co_author = f"\n\nCo-authored-by: {self.yuri_name} <{self.yuri_email}>"
            else:
                co_author = ""

            if not subject or "\n" in subject:
                raise ValueError("Invalid commit subject")

            if len(subject) > 72:
                subject = subject[:69].rstrip(" .") + "..."

            if not COMMIT_SUBJECT_RE.match(subject):
                raise ValueError(f"Commit subject is not conventional: {subject}")

            if not body:
                body = fallback.split("\n\n", 1)[1].strip() if "\n\n" in fallback else ""

            return subject + "\n\n" + body.strip() + co_author + "\n"

        except Exception as exc:
            write_debug("commit-message-fallback.txt", f"Falling back to heuristic commit message.\nReason: {type(exc).__name__}: {exc}\n")
            if self.yuri_name and self.yuri_email:
                return fallback + f"\n\nCo-authored-by: {self.yuri_name} <{self.yuri_email}>\n"
            return fallback

    def write_commit_message_file(self, changed_files: list[str]) -> Path:
        message = self.generate_commit_message(changed_files)
        # Write scrubbed version as debug artifact (may contain Co-authored-by email)
        write_debug("commit-message.txt", message)
        # Write real version to a temp file for git commit (not uploaded as artifact)
        fd, tmp_path = tempfile.mkstemp(suffix=".txt")
        os.write(fd, message.encode("utf-8"))
        os.close(fd)
        return Path(tmp_path)

    def commit_and_push_wip(self, reason: str) -> str | None:
        git(["config", "user.name", self.commit_name])
        git(["config", "user.email", self.commit_email])

        changed = git(["ls-files", "--modified", "--others", "--exclude-standard"]).splitlines()
        if not changed:
            return None

        subject = f"chore(wip): partial progress ({reason})"
        body = f"The agent stopped before completing the task.\n\nReason: {reason}\n\nChanged files:\n" + "\n".join(f"- {f}" for f in changed)

        # Write scrubbed version as debug artifact
        write_debug("wip-commit.txt", f"{subject}\n\n{body}")
        # Write real version to temp file for git commit
        fd, tmp_path = tempfile.mkstemp(suffix=".txt")
        os.write(fd, f"{subject}\n\n{body}".encode("utf-8"))
        os.close(fd)
        path = Path(tmp_path)

        run_cmd(["git", "add", "--", *changed], capture=True)
        git(["commit", "--no-verify", "-F", str(path)])
        os.unlink(path)

        branch = self.pr_info["headRefName"] if self.pr_info else getattr(self, "solve_branch", "")
        if not branch:
            print("WIP commit skipped: no branch to push to (no pr_info or solve_branch)")
            return None

        git(["push", "origin", f"HEAD:{branch}"])

        return git(["rev-parse", "--short", "HEAD"]).strip()

    def commit_and_push_fix(self) -> str:
        if not self.pr_info:
            raise RuntimeError("PR info missing")

        git(["config", "user.name", self.commit_name])
        git(["config", "user.email", self.commit_email])

        changed = git(["ls-files", "--modified", "--others",
                      "--exclude-standard"]).splitlines()
        if not changed:
            return ""

        commit_message_path = self.write_commit_message_file(changed)

        run_cmd(["git", "add", "--", *changed], capture=True)
        git(["commit", "--no-verify", "-F", str(commit_message_path)])
        os.unlink(commit_message_path)

        head_ref = self.pr_info["headRefName"]
        git(["push", "origin", f"HEAD:{head_ref}"])

        return git(["rev-parse", "--short", "HEAD"]).strip()

    def commit_and_push_solve(self) -> str:

        git(["config", "user.name", self.commit_name])
        git(["config", "user.email", self.commit_email])

        changed = git(["ls-files", "--modified", "--others",
                      "--exclude-standard"]).splitlines()
        if not changed:
            return ""

        commit_message_path = self.write_commit_message_file(changed)

        run_cmd(["git", "add", "--", *changed], capture=True)
        git(["commit", "--no-verify", "-F", str(commit_message_path)])
        os.unlink(commit_message_path)
        git(["push", "origin", f"HEAD:{self.solve_branch}"])

        return git(["rev-parse", "--short", "HEAD"]).strip()

    def create_solve_pr(self) -> str:
        if not self.issue_info:
            raise RuntimeError("Issue info missing")
        title = self.issue_info.get("title", f"Issue #{self.issue_number}")
        body = f"Closes #{self.issue_number}\n\n{scrub_secrets(self.final_summary)}"
        out = gh([
            "pr",
            "create",
            "--repo",
            self.repo,
            "--base",
            self.default_branch,
            "--head",
            self.solve_branch,
            "--title",
            f"Fix issue #{self.issue_number}: {title}",
            "--body",
            body,
        ])
        return out.strip()

    def handle_triage(self) -> None:
        self.create_progress_comment("⏳ I am triaging this issue...")
        self.update_task_checklist("Issue Triage", [("Fetching issues", False), ("Generating response", False)])

        try:
            issues_json = gh(["issue", "list", "--state", "open", "--json", "number,title,body", "--limit", "80", "--repo", self.repo])
            other_issues = json.loads(issues_json)
            other_issues = [i for i in other_issues if i["number"] != self.issue_number]
        except Exception as e:
            print(f"Failed to fetch issues: {e}")
            other_issues = []

        try:
            labels_config = load_labels()
            labels_json = json.dumps([{"name": l["name"], "description": l.get("description", "")} for l in labels_config], indent=2)
            labels_by_name = {x["name"].lower(): x for x in labels_config}
        except Exception as e:
            print(f"Failed to load labels: {e}")
            labels_json = "[]"
            labels_by_name = {}

        system_prompt = (
            "You are Ella Mizuki, a charismatic female AI assistant. The repository owner is Yuri (the developer who set you up). You are not Yuri - you are Ella. Write in English with a warm, charismatic tone. Use first-person ('I'). Never refer to yourself in third person.\n\n"
            "Check if the new issue duplicates an existing open issue. Then respond based on the scenario:\n\n"
            "NOT A DUPLICATE:\n"
            "Greet the user warmly, acknowledge the issue, and say Yuri will look into it. Don't mention other issues.\n"
            "Add `ASSIGN: yes` on a new line at the end so Yuri gets assigned.\n\n"
            "DUPLICATE:\n"
            "Greet the user, explain the issue is similar to an existing one (mention by number, e.g., #123). "
            "Say you'll close this one so they can follow the original. Don't mention Yuri or assignment.\n"
            "Add `DUPLICATE_OF: #123` on a new line at the end (replace 123 with the actual number). Don't include `ASSIGN: yes`.\n\n"
            "LABELS (non-duplicates only):\n"
            "Assign the most relevant labels from this list:\n"
            f"{labels_json}\n"
            "If any apply, add `LABELS: label1, label2` on a new line at the end."
        )
        
        if getattr(self, "repo_instructions", ""):
            system_prompt += f"\n\nHere are some global repository instructions you MUST follow:\n{self.repo_instructions}"

        issue_title = self.issue.get("title", "")
        issue_body = self.issue.get("body", "")
        issue_author = self.issue.get("user", {}).get("login", "unknown")

        context = f"New Issue:\nTitle: {issue_title}\nAuthor: @{issue_author}\nBody: {issue_body}\n\nOther Open Issues:\n{json.dumps(other_issues, indent=2)}"

        self.update_task_checklist("Issue Triage", [("Fetching issues", True), ("Generating response", False)])

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context}
        ]
        try:
            content_resp, _ = self.ai_call(messages, MAX_TOKENS.get("triage", 8192), use_small=True)
        except Exception as exc:
            print(f"AI call failed during triage: {exc}")
            self.update_progress("❌ I could not generate a triage response. The AI endpoint returned an error.")
            return
        response = content_resp or ""
        
        self.update_task_checklist("Issue Triage", [("Fetching issues", True), ("Generating response", True)])
        
        match_duplicate = re.search(r"DUPLICATE_OF:\s*#(\d+)", response)
        match_labels = re.search(r"LABELS:\s*(.+)", response)
        match_assign = re.search(r"ASSIGN:\s*yes", response, re.IGNORECASE)

        if match_assign:
            response = response.replace(match_assign.group(0), "").strip()

        if match_labels:
            response = response.replace(match_labels.group(0), "").strip()
            labels_str = match_labels.group(1)
            picked = []
            for item in labels_str.split(","):
                name = item.strip().lower()
                if name in labels_by_name and name not in picked:
                    picked.append(name)
            
            for name in picked:
                try:
                    gh(["issue", "edit", str(self.issue_number), "--repo", self.repo, "--add-label", labels_by_name[name]["name"]])
                except Exception as e:
                    print(f"Failed to add label {name}: {e}")

        if match_duplicate:
            duplicate_id = match_duplicate.group(1)
            # Remove the secret keyword so the user doesn't see it looking weird
            response = response.replace(match_duplicate.group(0), "").strip()
            # Append the standard GitHub duplicate phrase so GitHub's UI detects it
            response += f"\n\nDuplicate of #{duplicate_id}"
            
            self.comment(response)
            
            try:
                # Close the issue explicitly as a duplicate using the GitHub API
                gh([
                    "api",
                    "--method", "PATCH",
                    f"repos/{self.repo}/issues/{self.issue_number}",
                    "-f", "state=closed",
                    "-f", "state_reason=duplicate"
                ])
            except Exception as e:
                print(f"Failed to close issue as duplicate: {e}")
        else:
            if match_assign:
                try:
                    repo_owner = self.event.get("repository", {}).get("owner", {}).get("login", "")
                    if repo_owner:
                        gh(["issue", "edit", str(self.issue_number), "--repo", self.repo, "--add-assignee", repo_owner])
                except Exception as e:
                    print(f"Failed to assign user: {e}")
            self.comment(response)

    def handle_wiki(self) -> None:
        self.create_progress_comment("⏳ I am generating the Wiki documentation. Give me a moment to read the repository...")
        self.update_task_checklist("Generating Wiki Documentation", [("Reading repository", False), ("Generating pages", False), ("Pushing to wiki", False)])

        self.load_repo_instructions()
        self.allowed_files = self.get_repo_files()

        files_content = []
        for path_str in self.allowed_files:
            if path_str.startswith(".ella/") or path_str.startswith(".ella\\"):
                continue
                
            path = Path(path_str)
            if path.exists() and path.is_file():
                ext = path.suffix.lower()
                if ext in [".png", ".jpg", ".jpeg", ".gif", ".mp4", ".ico", ".woff", ".woff2", ".ttf"]:
                    continue
                text = read_text_limited(path, MAX_CONTEXT_FILE_BYTES)
                if text:
                    files_content.append(f"--- File: {path_str} ---\n{text}\n")

        context_str = "\n".join(files_content)[:MAX_CONTEXT_REPO_FILES_BYTES]

        system_prompt = (
            f"You are Ella Mizuki, a charismatic female AI assistant generating GitHub Wiki documentation for the '{self.repo}' repository. "
            "Write in English with a clear, friendly tone. "
            "Analyze the codebase and generate a comprehensive multi-page wiki. "
            "Divide into logical pages (Home.md, Setup.md, Architecture.md, etc.). "
            "Include project overview, setup instructions, architecture, and relevant details. "
            f"Use 'https://github.com/{self.repo}.git' for clone URLs and '{self.repo.split('/')[-1]}' as the directory name. "
            "Do NOT invent project name origins. Stick to facts in the provided code. "
            "Format each page with this syntax:\n\n"
            "---FILENAME: Home.md---\n# Home\nContent...\n\n"
            "---FILENAME: Setup.md---\n# Setup\nContent..."
        )

        self.update_task_checklist("Generating Wiki Documentation", [("Reading repository", True), ("Generating pages", False), ("Pushing to wiki", False)])

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_str}
            ]
            content_resp, _ = self.ai_call(messages, 8192, use_small=True)
            wiki_content = content_resp or ""
            
            self.update_task_checklist("Generating Wiki Documentation", [("Reading repository", True), ("Generating pages", True), ("Pushing to wiki", False)])
            pages = parse_markdown_files(wiki_content)
            
            if not pages:
                raise ValueError("AI did not return any valid markdown files.")

            self.update_progress("✅ I have generated the multi-page documentation. Pushing to the wiki repository...")

            token = os.environ.get("GH_TOKEN")
            if not token:
                raise RuntimeError("GH_TOKEN is missing")

            wiki_dir = Path(tempfile.mkdtemp())
            wiki_url = f"https://x-access-token:{token}@github.com/{self.repo}.wiki.git"

            try:
                git(["clone", "--depth", "1", wiki_url, str(wiki_dir)])
            except CommandError:
                run_cmd(["git", "init", str(wiki_dir)], capture=True)
                run_cmd(["git", "-C", str(wiki_dir), "checkout", "-b", "master"], capture=True)

            for filename, content in pages.items():
                if not filename.endswith(".md"):
                    filename += ".md"
                safe_filename = filename.replace("/", "_").replace("\\", "_")
                file_path = wiki_dir / safe_filename
                file_path.write_text(str(content), encoding="utf-8")

            run_cmd(["git", "-C", str(wiki_dir), "config", "user.name", self.commit_name], capture=True)
            run_cmd(["git", "-C", str(wiki_dir), "config", "user.email", self.commit_email], capture=True)
            run_cmd(["git", "-C", str(wiki_dir), "add", "."], capture=True)

            msg = "docs: generate multi-page wiki documentation via Ella"
            if self.yuri_name and self.yuri_email:
                msg += f"\n\nCo-authored-by: {self.yuri_name} <{self.yuri_email}>"

            run_cmd(["git", "-C", str(wiki_dir), "commit", "-m", msg], capture=True)
            run_cmd(["git", "-C", str(wiki_dir), "push", "origin", "master"], capture=True)

            shutil.rmtree(wiki_dir, ignore_errors=True)

            self.update_task_checklist("Generating Wiki Documentation", [("Reading repository", True), ("Generating pages", True), ("Pushing to wiki", True)], "✅ The Wiki documentation has been successfully generated and pushed! Check your repository's Wiki tab.")

        except Exception as e:
            self.update_task_checklist("Generating Wiki Documentation", [("Reading repository", True), ("Generating pages", True), ("Pushing to wiki", False)], f"❌ I encountered an error while generating or pushing the Wiki: {e}\n\nMake sure I have Wiki write permissions!")
            print(f"Wiki error: {e}")

def main() -> int:
    try:
        Ella().run()
        return 0
    except Exception as exc:
        msg = scrub_secrets(f"{type(exc).__name__}: {exc}\n")
        write_debug("fatal-error.txt", msg)
        print(f"Fatal error: {scrub_secrets(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
