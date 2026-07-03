"""Test that tail_text returns the expected number of lines."""
import os
import importlib.util
import pytest

@pytest.fixture
def utils_module():
    spec = importlib.util.spec_from_file_location("agent", ".ella/agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tail_text_returns_exact_lines(utils_module):
    """tail_text should return at most N lines from the end of a file."""
    import tempfile
    from pathlib import Path
    tail_text = utils_module.tail_text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for i in range(100):
            f.write(f"Line {i}\n")
        path = Path(f.name)
    try:
        result = tail_text(path, 10)
        lines = result.strip().split("\n")
        assert len(lines) == 10, f"Expected 10 lines, got {len(lines)}"
        assert "Line 90" in lines[0]
    finally:
        path.unlink()
