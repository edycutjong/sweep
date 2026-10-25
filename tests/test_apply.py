"""Acceptance #3: --apply deletes exactly the SAFE items, after the typed confirmation, and nothing else."""

import json

from conftest import Recorder, tree

from sweep import apply, plan, scan


def planned(ctx, verdict="safe"):
    return plan.classify(scan.scan(ctx), ctx, Recorder(verdict))


def test_apply_deletes_exactly_the_safe_items(mac, tmp_path):
    items = planned(mac)
    safe = [it for it in items if it.verdict == "safe"]
    targets = apply.deletable(items, mac)
    assert {it.path for it in targets} == {it.path for it in safe}
    before = tree(tmp_path)
    log = apply.apply(items, mac, ask=lambda _: apply.confirm_phrase(targets), say=lambda _: None)

    gone = {
        p
        for p in before
        if any(str(tmp_path / p).startswith(it.path + "/") or str(tmp_path / p) == it.path for it in safe)
    }
    assert gone, "fixture should have SAFE items"
    assert tree(tmp_path) == (before - gone) | {"state/last-run.json"}
    for must_stay in (
        "home/Documents/notes.txt",
        "home/code/old-clean/src/index.js",
        "home/code/dirty/node_modules/pkg/index.js",
        "home/Downloads/installer.dmg",
        "tmp/fresh/socket.lock",
        "outside/proj/node_modules/pkg/index.js",
        "outside/precious/thesis.txt",
        "home/code/nomarker/target/data.bin",
    ):
        assert must_stay in tree(tmp_path), must_stay
    saved = json.loads((tmp_path / "state/last-run.json").read_text())
    assert {r["path"] for r in saved["removed"]} == {it.path for it in safe}
    assert saved["freed_bytes"] == sum(it.size for it in safe) == log["freed_bytes"]
    assert saved["failed"] == []


def test_wrong_phrase_cancels(mac, tmp_path):
    before = tree(tmp_path)
    out = apply.apply(planned(mac), mac, ask=lambda _: "yes", say=lambda _: None)
    assert out["confirmed"] is False and tree(tmp_path) == before


def test_eof_cancels(mac, tmp_path):
    def eof(_):
        raise EOFError

    before = tree(tmp_path)
    assert apply.apply(planned(mac), mac, ask=eof, say=lambda _: None)["removed"] == []
    assert tree(tmp_path) == before


def test_forged_safe_verdicts_outside_the_guard_are_not_deleted(mac, tmp_path):
    items = planned(mac, "ask")
    for it in items:
        it.verdict = "safe"  # pretend something upstream went wrong
    targets = apply.deletable(items, mac)
    kinds = {it.kind for it in targets}
    assert "docker" not in kinds and "downloads" not in kinds and "trash" not in kinds
    apply.apply(items, mac, ask=lambda _: apply.confirm_phrase(targets), say=lambda _: None)
    left = tree(tmp_path)
    assert "home/Downloads/installer.dmg" in left and "home/.Trash/old.txt" in left
    assert "outside/precious/thesis.txt" in left and "home/Documents/notes.txt" in left
    assert "home/code/dirty/node_modules/pkg/index.js" in left  # rule KEEP survives a forged SAFE
    assert "home/code/recent/node_modules/pkg/index.js" in left
    assert "home/code/nomarker/target/data.bin" in left and "tmp/fresh/socket.lock" in left


def test_nothing_safe_removes_nothing(mac, tmp_path):
    before = tree(tmp_path)
    out = apply.apply(planned(mac, "keep"), mac, ask=lambda _: "DELETE 0.0 GB", say=lambda _: None)
    assert out["removed"] == [] and tree(tmp_path) == before
