"""Test load_labels handles missing color field gracefully."""
import importlib.util
import json
from pathlib import Path
import pytest

@pytest.fixture
def utils():
    spec = importlib.util.spec_from_file_location("agent", ".ella/agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_labels_missing_color(utils, monkeypatch, tmp_path):
    """load_labels should use default color when color field is missing."""
    labels_file = tmp_path / "labels.json"
    labels_file.write_text(json.dumps([
        {"name": "bug", "description": "A bug report"}
    ]))

    original_exists = Path.exists

    def mock_exists(self):
        if str(self).endswith("labels.json"):
            return True
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", mock_exists)
    monkeypatch.setattr(utils, "AGENT_DIR", tmp_path)

    result = utils.load_labels()
    assert len(result) == 1
    assert result[0]["name"] == "bug"
    assert result[0]["color"] == "ededed"
