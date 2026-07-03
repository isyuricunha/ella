"""Tests for detect_check_commands and detect_install_commands.

These tests create temporary repos with various marker files and mock
command_exists to control which tools are "available".
"""

import importlib.util
import json
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
    """Patch ROOT/ROOT_RESOLVED to a temp dir and return it."""
    monkeypatch.setattr(agent, "ROOT", tmp_path)
    monkeypatch.setattr(agent, "ROOT_RESOLVED", tmp_path.resolve())
    return tmp_path


def _mock_command_exists(monkeypatch, available: set[str]):
    """Mock command_exists to return True only for commands in 'available'."""
    def fake(cmd: str) -> bool:
        return cmd in available
    monkeypatch.setattr(agent, "command_exists", fake)


def _mock_python_module_exists(monkeypatch, available: set[str]):
    """Mock python_module_exists to return True only for modules in 'available'."""
    def fake(self, module: str) -> bool:
        return module in available
    monkeypatch.setattr(agent.Ella, "python_module_exists", fake)


# --- detect_check_commands ---


class TestDetectCheckNode:
    def test_pnpm_runner(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text(
            json.dumps({"scripts": {"lint": "eslint .", "test": "vitest"}}))
        (temp_repo / "pnpm-lock.yaml").write_text("")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "node-lint" in names
        assert "node-test" in names
        assert ["pnpm", "run", "lint"] in [c[1] for c in checks]

    def test_npm_fallback(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text(
            json.dumps({"scripts": {"build": "tsc"}}))
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert ["npm", "run", "build"] in [c[1] for c in checks]

    def test_yarn_runner(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}}))
        (temp_repo / "yarn.lock").write_text("")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert ["yarn", "test"] in [c[1] for c in checks]

    def test_bun_runner(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text(
            json.dumps({"scripts": {"test": "bun test"}}))
        (temp_repo / "bun.lock").write_text("")
        _mock_command_exists(monkeypatch, {"bun"})
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert ["bun", "run", "test"] in [c[1] for c in checks]

    def test_no_scripts(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text("{}")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert all(not n.startswith("node-") for n, _ in checks)

    def test_invalid_package_json(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text("NOT JSON")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert all(not n.startswith("node-") for n, _ in checks)


class TestDetectCheckGo:
    def test_go_detected(self, temp_repo, monkeypatch):
        (temp_repo / "go.mod").write_text("module test\ngo 1.21\n")
        _mock_command_exists(monkeypatch, {"go"})
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "go-fmt" in names
        assert "go-vet" in names
        assert "go-test" in names

    def test_go_missing_command(self, temp_repo, monkeypatch):
        (temp_repo / "go.mod").write_text("module test\n")
        _mock_command_exists(monkeypatch, set())
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert all(not n.startswith("go-") for n, _ in checks)


class TestDetectCheckCargo:
    def test_cargo_detected(self, temp_repo, monkeypatch):
        (temp_repo / "Cargo.toml").write_text("[package]\nname = \"test\"\n")
        _mock_command_exists(monkeypatch, {"cargo"})
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "cargo-fmt" in names
        assert "cargo-clippy" in names
        assert "cargo-test" in names


class TestDetectCheckDotnet:
    def test_dotnet_detected(self, temp_repo, monkeypatch):
        (temp_repo / "Test.sln").write_text("")
        _mock_command_exists(monkeypatch, {"dotnet"})
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "dotnet-restore" in names
        assert "dotnet-build" in names
        assert "dotnet-test" in names

    def test_csproj_detected(self, temp_repo, monkeypatch):
        (temp_repo / "src").mkdir()
        (temp_repo / "src" / "App.csproj").write_text("")
        _mock_command_exists(monkeypatch, {"dotnet"})
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert any(n.startswith("dotnet-") for n, _ in checks)


class TestDetectCheckGradle:
    def test_gradle_detected(self, temp_repo, monkeypatch):
        (temp_repo / "build.gradle").write_text("")
        (temp_repo / "gradlew").write_text("#!/bin/sh\n")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "gradle-test" in names

    def test_gradle_missing_wrapper(self, temp_repo, monkeypatch):
        (temp_repo / "build.gradle").write_text("")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert all(not n.startswith("gradle-") for n, _ in checks)


class TestDetectCheckPython:
    def test_pytest_detected(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text("[tool.pytest]\n")
        _mock_command_exists(monkeypatch, {"pytest"})
        _mock_python_module_exists(monkeypatch, set())
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "python-pytest" in names

    def test_ruff_via_command(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text("")
        _mock_command_exists(monkeypatch, {"ruff"})
        _mock_python_module_exists(monkeypatch, set())
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "python-ruff" in names
        assert ["ruff", "check", "."] in [c[1] for c in checks]

    def test_ruff_via_module(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text("")
        _mock_command_exists(monkeypatch, set())
        _mock_python_module_exists(monkeypatch, {"ruff"})
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "python-ruff" in names
        assert [sys.executable, "-m", "ruff", "check", "."] in [c[1] for c in checks]

    def test_no_python_tools(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text("")
        _mock_command_exists(monkeypatch, set())
        _mock_python_module_exists(monkeypatch, set())
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert all(not n.startswith("python-") for n, _ in checks)


class TestDetectCheckPhp:
    def test_phpunit_detected(self, temp_repo, monkeypatch):
        (temp_repo / "composer.json").write_text("{}")
        (temp_repo / "vendor").mkdir()
        (temp_repo / "vendor" / "bin").mkdir()
        (temp_repo / "vendor" / "bin" / "phpunit").write_text("#!/bin/sh\n")
        (temp_repo / "vendor" / "bin" / "phpstan").write_text("#!/bin/sh\n")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "phpunit" in names
        assert "phpstan" in names


class TestDetectCheckStandaloneTestPy:
    def test_test_py_detected(self, temp_repo, monkeypatch):
        (temp_repo / "test.py").write_text("print('test')")
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        names = [c[0] for c in checks]
        assert "test.py" in names


class TestDetectCheckEmpty:
    def test_empty_repo(self, temp_repo, monkeypatch):
        _mock_command_exists(monkeypatch, set())
        _mock_python_module_exists(monkeypatch, set())
        ella = _make_ella_shell()
        checks = ella.detect_check_commands()
        assert checks == []


# --- detect_install_commands ---


class TestDetectInstallNode:
    def test_pnpm_detected(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text("{}")
        (temp_repo / "pnpm-lock.yaml").write_text("")
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "pnpm" in names
        assert any("pnpm install" in " ".join(c[1]) for c in commands)

    def test_npm_detected(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text("{}")
        (temp_repo / "package-lock.json").write_text("")
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "npm" in names

    def test_yarn_detected(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text("{}")
        (temp_repo / "yarn.lock").write_text("")
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "yarn" in names

    def test_bun_with_lock(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text("{}")
        (temp_repo / "bun.lock").write_text("")
        _mock_command_exists(monkeypatch, {"bun"})
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "bun" in names
        assert "--frozen-lockfile" in commands[0][1]

    def test_bun_without_lock(self, temp_repo, monkeypatch):
        (temp_repo / "package.json").write_text("{}")
        _mock_command_exists(monkeypatch, {"bun"})
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "bun" in names
        assert "--frozen-lockfile" not in commands[0][1]


class TestDetectInstallPython:
    def test_uv_detected(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text("")
        (temp_repo / "uv.lock").write_text("")
        _mock_command_exists(monkeypatch, {"uv"})
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "uv" in names

    def test_poetry_detected(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text("")
        (temp_repo / "poetry.lock").write_text("")
        _mock_command_exists(monkeypatch, {"poetry"})
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "poetry" in names

    def test_requirements_txt(self, temp_repo, monkeypatch):
        (temp_repo / "requirements.txt").write_text("requests\n")
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "pip" in names

    def test_pip_editable_fallback(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text(
            "[build-system]\nbuild-backend = \"hatchling.build\"\n"
            "[tool.hatch.build.targets.wheel]\npackages = [\"src/mypkg\"]\n"
        )
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "pip-editable" in names

    def test_pyproject_no_build_target_skips_pip_editable(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text(
            "[build-system]\nbuild-backend = \"hatchling.build\"\n"
            "[tool.hatch.build.targets.wheel]\npackages = []\n"
        )
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "pip-editable" not in names

    def test_pyproject_empty_no_install(self, temp_repo, monkeypatch):
        (temp_repo / "pyproject.toml").write_text("")
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "pip-editable" not in names


class TestDetectInstallOther:
    def test_composer_detected(self, temp_repo, monkeypatch):
        (temp_repo / "composer.json").write_text("{}")
        _mock_command_exists(monkeypatch, {"composer"})
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        names = [c[0] for c in commands]
        assert "composer" in names

    def test_empty_repo(self, temp_repo, monkeypatch):
        _mock_command_exists(monkeypatch, set())
        ella = _make_ella_shell()
        commands = ella.detect_install_commands()
        assert commands == []
