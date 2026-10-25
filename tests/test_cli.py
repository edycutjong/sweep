import json

import pytest
from conftest import Recorder, tree

from sweep import catalogue, cli


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
    assert phrases and phrases[0].startswith('Type "DELETE ')
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
