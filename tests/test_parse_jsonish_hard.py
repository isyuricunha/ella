"""Hard tests for parse_jsonish edge cases."""
import importlib.util
import pytest


@pytest.fixture
def utils():
    spec = importlib.util.spec_from_file_location("agent", ".ella/agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_object_with_trailing_semicolon(utils):
    """JSON followed by a semicolon (common AI artifact) should still parse.

    The AI sometimes appends ';' after JSON. json.loads fails on the full
    string, so parse_jsonish must use the fallback extraction path.
    """
    result = utils.parse_jsonish('{"labels": ["bug"]};')
    assert result == {"labels": ["bug"]}


def test_parse_object_with_leading_prefix(utils):
    """JSON with a leading word prefix should extract correctly via fallback.

    json.loads fails on 'Action: {"labels": ["bug"]}', so the fallback
    find/rfind path must correctly extract the object.
    """
    result = utils.parse_jsonish('Result: {"labels": ["enhancement"], "assign": true}')
    assert result == {"labels": ["enhancement"], "assign": True}


def test_parse_nested_empty_object(utils):
    """Nested empty objects inside a larger JSON should parse correctly.

    The key test: rfind('}') must find the LAST brace, not the first.
    If the extraction uses the wrong end index, the nested object gets
    truncated and json.loads raises.
    """
    result = utils.parse_jsonish('Here is my plan:\n{"steps": [{"action": "edit"}, {}], "done": true}\nLet me know.')
    assert result == {"steps": [{"action": "edit"}, {}], "done": True}
