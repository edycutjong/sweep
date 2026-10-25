"""Acceptance #2: the hard rules hold no matter what the model says."""

import os
from pathlib import Path

import pytest
from conftest import Recorder, write

from sweep import plan, rules, scan
from sweep.scan import Item


def run(ctx, judge):
    return {plan.display_path(it, ctx): it for it in plan.classify(scan.scan(ctx), ctx, judge)}


def test_dirty_repo_is_keep_even_if_model_says_safe(mac):
    got = run(mac, Recorder("safe"))
    it = got["~/code/dirty/node_modules"]
    assert (it.verdict, it.decided_by) == ("keep", "rule")
    assert "uncommitted" in it.reason


def test_recent_repo_is_keep(mac):
    it = run(mac, Recorder("safe"))["~/code/recent/node_modules"]
    assert (it.verdict, it.decided_by) == ("keep", "rule")


def test_old_clean_repo_can_be_safe(mac):
    assert run(mac, Recorder("safe"))["~/code/old-clean/node_modules"].verdict == "safe"


def test_downloads_and_trash_are_never_safe(mac):
    got = run(mac, Recorder("safe"))
    for p in ("~/Downloads/installer.dmg", "~/Downloads/old-folder", "~/.Trash"):
        assert got[p].verdict == "ask", p


def test_docker_is_ask_with_the_command_and_never_shown_to_the_model(mac):
    judge = Recorder("safe")
    docker = [it for it in run(mac, judge).values() if it.source == "docker"]
    assert len(docker) == 1 and docker[0].verdict == "ask"
    assert "docker system prune" in docker[0].reason
    assert all(m["kind"] != "docker" for m in judge.seen)


def test_only_catalogue_and_regenerable_items_inside_roots(mac):
    paths = set(run(mac, Recorder("safe")))
    assert not any("Documents" in p or "Desktop" in p for p in paths)
    assert not any("outside" in p or "precious" in p for p in paths)
    assert "~/code/linky/node_modules" not in paths  # symlink: never followed, never a candidate
    assert not any(p.endswith(("src", "index.js", "package.json")) for p in paths)


def test_tmpdir_recent_is_keep_old_is_judged(mac):
    got = run(mac, Recorder("safe"))
    assert got["$TMPDIR/fresh"].verdict == "keep"
    assert got["$TMPDIR/old-build"].verdict == "safe"


def test_missing_regeneration_marker_caps_at_ask(mac):
    got = run(mac, Recorder("safe"))
    assert got["~/code/nomarker/target"].verdict == "ask"
    assert got["~/code/py/.venv"].verdict == "safe"


def test_model_cannot_downgrade_keep_but_can_raise_caution(mac):
    judge = Recorder("keep")
    got = run(mac, judge)
    assert got["~/code/old-clean/node_modules"].verdict == "keep"
    assert got["~/Downloads/installer.dmg"].verdict == "keep"
    shown = {m["id"] for m in judge.seen}
    assert got["~/code/dirty/node_modules"].id not in shown  # rule-final items are not even asked


def test_model_sees_metadata_only(mac):
    judge = Recorder("ask")
    run(mac, judge)
    allowed = {
        "id",
        "name",
        "kind",
        "size_mb",
        "age_days",
        "repo_last_commit_days",
        "in_git_repo",
        "repo_dirty",
    }
    assert judge.seen and all(set(m) <= allowed for m in judge.seen)
    assert not any(str(mac.home) in str(m) for m in judge.seen)  # never the absolute path


def test_path_guard(mac, tmp_path):
    def item(path, source="project", kind="node_modules"):
        return Item(id="x", path=str(path), kind=kind, source=source, size=1)

    assert rules.allowed_path(item(mac.home / "code/old-clean/node_modules"), mac)
    assert not rules.allowed_path(item(tmp_path / "outside/proj/node_modules"), mac)  # outside roots
    assert not rules.allowed_path(item(mac.home / "code/old-clean/src"), mac)  # not regenerable
    assert not rules.allowed_path(item(mac.home / "code/linky/node_modules"), mac)  # symlink
    assert not rules.allowed_path(item(mac.home, "catalogue", "app-cache"), mac)
    assert not rules.allowed_path(item(mac.home / "Documents", "catalogue", "app-cache"), mac)
    assert not rules.allowed_path(item(mac.home / "Library/Caches", "catalogue", "app-cache"), mac)
    assert not rules.allowed_path(item("/System", "catalogue", "app-cache"), mac)
    assert not rules.allowed_path(item(mac.tmpdir, "temp", "temp"), mac)
    assert rules.allowed_path(
        item(mac.home / "Library/Caches/com.example.app", "catalogue", "app-cache"), mac
    )
    assert not rules.allowed_path(Item(id="d", path="docker", kind="docker", source="docker", size=1), mac)


def test_unreadable_is_ask_not_zero(mac):
    trash = mac.home / ".Trash"
    os.chmod(trash, 0)
    try:
        it = run(mac, Recorder("safe"))["~/.Trash"]
    finally:
        os.chmod(trash, 0o755)
    assert it.size is None and it.verdict == "ask" and "unreadable" in it.reason


def test_more_cautious_order():
    assert rules.more_cautious("safe", "ask") == "ask"
    assert rules.more_cautious("keep", "safe") == "keep"
    assert rules.more_cautious("ask", "ask") == "ask"


def test_docker_size_parse():
    assert scan.parse_docker_size("25.3GB (80%)") == 25_300_000_000
    assert scan.parse_docker_size("512.1MB") == 512_100_000
    assert scan.parse_docker_size("0B") == 0
    assert scan.parse_docker_size("") == 0


def test_regenerable_name_without_build_signature_is_ask(mac):
    got = run(mac, Recorder("safe"))
    assert got["~/code/rust/target"].verdict == "safe"  # Cargo.toml beside + CACHEDIR.TAG inside
    assert got["~/code/maven-data/target"].verdict == "ask"  # pom.xml beside, but no build output inside
    assert got["~/code/scratch-app/node_modules"].verdict == "ask"  # no lockfile: cannot reproduce it


def test_project_outside_git_edited_recently_is_keep(mac):
    it = run(mac, Recorder("safe"))["~/code/live-app/node_modules"]
    assert (it.verdict, it.decided_by) == ("keep", "rule") and "no git repo" in it.reason


def test_partly_valid_batch_answers_what_it_can(mac):
    def half(batch):
        return {m["id"]: {"verdict": "safe", "reason": "ok"} for m in batch[::2]}

    items = [it for it in plan.classify(scan.scan(mac), mac, half) if it.decided_by != "rule"]
    assert {it.verdict for it in items if it.reason == plan.FALLBACK_REASON} == {"ask"}
    assert any(it.reason == plan.FALLBACK_REASON for it in items)


def test_tmpdir_and_roots_validation(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert scan.safe_tmpdir(str(home), home) is None  # TMPDIR=~ would expose home
    assert scan.safe_tmpdir("/", home) is None
    assert scan.safe_tmpdir("/private/var/folders/ab/xyz/T/", home) == Path("/private/var/folders/ab/xyz/T")
    for loose in (
        "/var/folders",
        "/private/var/folders/ab",
        "/tmp",
        "/private/tmp",
        "/private/var/folders/a/b",
    ):
        assert scan.safe_tmpdir(loose, home) is None, loose
    assert scan.validate_roots([str(home)], home) == (Path(os.path.realpath(home)),)
    for bad in ("/", str(tmp_path), str(home / "Library/Caches")):
        with pytest.raises(ValueError):
            scan.validate_roots([bad], home)


def test_guard_refuses_system_folders_and_a_home_tmpdir(mac):
    sys_item = Item(id="s", path="/usr/local/lib/node_modules", kind="node_modules", source="project", size=1)
    assert not rules.allowed_path(sys_item, mac)
    mac.tmpdir = mac.home
    tmp_item = Item(id="t", path=str(mac.home / "code"), kind="temp", source="temp", size=1)
    assert not rules.allowed_path(tmp_item, mac)


def test_lockfile_search_stops_at_the_root(mac):
    write(mac.home / "yarn.lock", "")  # a stray lockfile above the root must not vouch for anything
    assert run(mac, Recorder("safe"))["~/code/scratch-app/node_modules"].verdict == "ask"
