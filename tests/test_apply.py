"""Acceptance #3: --apply deletes exactly the SAFE items, after the typed confirmation, and nothing else."""

import json

import pytest
from conftest import Recorder, tree, write

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
    assert saved["removed_du_bytes"] == sum(it.size for it in safe)
    assert saved["freed_bytes"] == log["freed_bytes"] >= 0  # measured from the disk itself
    assert saved["free_space_before"] is not None and saved["free_space_after"] is not None
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


def test_activity_after_the_plan_blocks_the_delete(mac, tmp_path):
    items = planned(mac)
    targets = apply.deletable(items, mac)
    assert any(it.path.endswith("old-clean/node_modules") for it in targets)
    write(mac.home / "code/old-clean/src/index.js", "edited after the plan")  # repo is now dirty
    write(mac.tmpdir / "old-build/out.o", "rebuilt after the plan")  # temp entry is now in use
    out = apply.apply(items, mac, ask=lambda _: apply.confirm_phrase(targets), say=lambda _: None)
    left = tree(tmp_path)
    assert "home/code/old-clean/node_modules/pkg/index.js" in left
    assert "tmp/old-build/out.o" in left
    skipped = {f["path"] for f in out["failed"]}
    assert any(p.endswith("old-clean/node_modules") for p in skipped)


def test_every_target_is_listed_before_the_prompt(mac):
    items = planned(mac)
    lines: list[str] = []
    apply.apply(items, mac, ask=lambda _: "no", say=lines.append)
    for it in apply.deletable(items, mac):
        assert any(plan.display_path(it, mac) in line for line in lines), it.path


def test_unwritable_log_does_not_crash(mac, tmp_path):
    (tmp_path / "state").write_text("a file where the state folder should be")
    items = planned(mac)
    targets = apply.deletable(items, mac)
    lines: list[str] = []
    out = apply.apply(items, mac, ask=lambda _: apply.confirm_phrase(targets), say=lines.append)
    assert out["removed"] and "could not write the log" in lines[-1]


def test_editing_a_non_git_project_after_the_plan_blocks_its_venv(mac, tmp_path):
    items = planned(mac)
    targets = apply.deletable(items, mac)
    assert any(it.path.endswith("py/.venv") for it in targets)
    write(mac.home / "code/py/main.py", "new work, no git")
    apply.apply(items, mac, ask=lambda _: apply.confirm_phrase(targets), say=lambda _: None)
    assert "home/code/py/.venv/pyvenv.cfg" in tree(tmp_path)


def test_interrupted_delete_still_writes_the_log(mac, tmp_path, monkeypatch):
    items = planned(mac)
    targets = apply.deletable(items, mac)
    calls = []

    def rmtree_then_ctrl_c(path):
        calls.append(path)
        if len(calls) == 2:
            raise KeyboardInterrupt
        real_rmtree(path)

    real_rmtree = apply.shutil.rmtree
    monkeypatch.setattr(apply.shutil, "rmtree", rmtree_then_ctrl_c)
    with pytest.raises(KeyboardInterrupt):
        apply.apply(items, mac, ask=lambda _: apply.confirm_phrase(targets), say=lambda _: None)
    saved = json.loads((tmp_path / "state/last-run.json").read_text())
    assert len(saved["removed"]) == 1
