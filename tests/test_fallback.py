"""Acceptance #4: any model failure degrades to ASK — never crashes, never SAFE."""

import io
import json

import pytest

from sweep import model, plan, scan


def judged(ctx, judge):
    return [it for it in plan.classify(scan.scan(ctx), ctx, judge) if it.decided_by != "rule"]


def assert_all_ask(items):
    assert items and all(it.verdict == "ask" for it in items)
    assert all(it.reason == plan.FALLBACK_REASON for it in items)


def test_judge_that_raises(mac):
    def boom(batch):
        raise RuntimeError("model exploded")

    assert_all_ask(judged(mac, boom))


@pytest.mark.parametrize(
    "answer", [None, [], "nope", {"i1": "safe"}, {"i1": {"verdict": "delete", "reason": "x"}}]
)
def test_judge_with_garbage_answers(mac, answer):
    assert_all_ask(judged(mac, lambda batch: answer))


def test_no_key_means_ask(mac):
    assert_all_ask(judged(mac, model.judge))  # conftest removes every key source


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize(
    "content",
    ["not json", '```json\n{"items": []}\n```', json.dumps({"items": [{"id": "i1", "verdict": "safe"}]})],
)
def test_bad_json_from_the_real_client_means_ask(mac, monkeypatch, content):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    monkeypatch.setattr(model.urllib.request, "urlopen", lambda *a, **k: FakeResponse(body))
    assert_all_ask(judged(mac, model.judge))


def test_timeout_means_ask(mac, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def slow(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(model.urllib.request, "urlopen", slow)
    assert_all_ask(judged(mac, model.judge))
