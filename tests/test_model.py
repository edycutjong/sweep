import json
import urllib.error

from sweep import model

IDS = {"a", "b"}


def test_parses_valid_contract():
    content = json.dumps(
        {
            "items": [
                {"id": "a", "verdict": "safe", "reason": "Cache."},
                {"id": "b", "verdict": "keep", "reason": "Active."},
            ]
        }
    )
    assert model.parse_verdicts(content, IDS) == {
        "a": {"verdict": "safe", "reason": "Cache."},
        "b": {"verdict": "keep", "reason": "Active."},
    }


def test_rejects_bad_json_and_fences():
    assert model.parse_verdicts("not json", IDS) == {}
    assert model.parse_verdicts('```json\n{"items": []}\n```', IDS) == {}
    assert model.parse_verdicts(None, IDS) == {}
    assert model.parse_verdicts("[]", IDS) == {}


def test_drops_bad_entries():
    content = json.dumps(
        {
            "items": [
                {"id": "a", "verdict": "delete", "reason": "x"},  # unknown verdict
                {"id": "zzz", "verdict": "safe", "reason": "x"},  # unknown id
                {"id": "b", "verdict": "safe", "reason": ""},  # empty reason
                {"id": "b", "verdict": "safe", "reason": "ok", "extra": 1},  # extra key
            ]
        }
    )
    assert model.parse_verdicts(content, IDS) == {}


def test_first_entry_per_id_wins():
    content = json.dumps(
        {
            "items": [
                {"id": "a", "verdict": "keep", "reason": "1"},
                {"id": "a", "verdict": "safe", "reason": "2"},
            ]
        }
    )
    assert model.parse_verdicts(content, IDS) == {"a": {"verdict": "keep", "reason": "1"}}


def test_no_key_returns_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(model, "CREDENTIALS", tmp_path / "missing.json")
    assert model.judge([{"id": "a"}]) == {}


def test_network_failure_returns_nothing(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def boom(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(model.urllib.request, "urlopen", boom)
    assert model.judge([{"id": "a"}]) == {}
