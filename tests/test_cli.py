import json

import pytest
from conftest import Recorder, tree, write

from sweep import catalogue, cli, reminder


def test_dry_run_prints_groups_and_footer(mac, tmp_path, capsys):
    before = tree(tmp_path)
    assert cli.main([], ctx=mac, judge=Recorder("safe")) == 0
    out = capsys.readouterr().out
    for word in ("SAFE", "ASK", "KEEP", "found", "safe", "model google/gemma-4-31b-it"):
        assert word in out
    assert tree(tmp_path) == before  # the dry run deletes nothing


def test_json_plan(mac, capsys):
    assert cli.main(["--json"], ctx=mac, judge=Recorder("safe")) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["model"] == "google/gemma-4-31b-it"
    assert data["safe_bytes"] > 0 and sum(data["counts"].values()) == len(data["items"])
    assert all(not i["path"].startswith(str(mac.home)) for i in data["items"])


def test_apply_without_a_terminal_refuses(mac, tmp_path, capsys):
    before = tree(tmp_path)
    assert cli.main(["--apply"], ctx=mac, judge=Recorder("safe")) == 1
    assert tree(tmp_path) == before


def test_apply_with_typed_confirmation(mac, tmp_path, capsys):
    phrases = []

    def ask(prompt):
        phrases.append(prompt)
        return prompt.split('"')[1]

    assert cli.main(["--apply"], ctx=mac, judge=Recorder("safe"), ask=ask) == 0
    assert phrases and 'Type "DELETE ' in phrases[0]
    assert "home/code/old-clean/node_modules/pkg/index.js" not in tree(tmp_path)
    assert "freed" in capsys.readouterr().out


def test_json_and_apply_are_exclusive():
    with pytest.raises(SystemExit):
        cli.main(["--json", "--apply"])


def test_version_names_the_model(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert "gemma" in capsys.readouterr().out


def test_catalogue_paths_are_relative_and_unique():
    paths = [loc.path for loc in catalogue.MACOS_LOCATIONS]
    assert len(paths) == len(set(paths))
    assert all(not p.startswith("/") for p in paths)


def test_markup_in_names_and_reasons_does_not_crash(mac, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "250")
    write(mac.home / "Downloads/report [final] [red].pdf")

    def odd(batch):
        return {m["id"]: {"verdict": "ask", "reason": "closing tag [/oops] and [bold]"} for m in batch}

    assert cli.main(["--top", "100"], ctx=mac, judge=odd) == 0
    out = capsys.readouterr().out
    assert "[/oops]" in out and "report [final] [red].pdf" in out


def test_bad_root_exits_2_without_scanning(monkeypatch, capsys):
    def bad(*a, **k):
        raise ValueError("--root / must be your home folder or a folder inside it (not ~/Library)")

    monkeypatch.setattr(cli.scan.Context, "default", classmethod(bad))
    assert cli.main(["--root", "/"]) == 2
    assert "must be your home folder" in capsys.readouterr().err


def test_dry_run_says_nothing_was_deleted_and_how_sizes_are_counted(mac, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "250")
    cli.main([], ctx=mac, judge=Recorder("safe"))
    out = capsys.readouterr().out
    assert "nothing was deleted" in out and "hard-linked" in out and "(du)" in out
    assert "docker system prune" in out


def test_notify_runs_a_dry_run_and_shows_one_notification(mac, tmp_path):
    before = tree(tmp_path)
    shown = []
    assert cli.main(["--notify"], ctx=mac, judge=Recorder("safe"), notifier=shown.append) == 0
    assert len(shown) == 1 and "GB (du)" in shown[0]
    assert tree(tmp_path) == before


def test_install_reminder_writes_a_plist_and_loads_nothing(tmp_path, monkeypatch, capsys):
    import plistlib
    import subprocess

    def boom(*a, **k):
        raise AssertionError("launchctl / any subprocess must not run")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(reminder, "LOG", tmp_path / "dot-sweep" / "reminder.log")
    target = tmp_path / "LaunchAgents" / "reminder.plist"
    assert cli.main(["--install-reminder", str(target)]) == 0
    job = plistlib.loads(target.read_bytes())
    assert job["ProgramArguments"][-1] == "--notify" and "--apply" not in job["ProgramArguments"]
    assert job["StartCalendarInterval"]["Weekday"] == 0
    assert "launchctl bootstrap" in capsys.readouterr().out
