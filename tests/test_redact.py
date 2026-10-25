import json

import pytest
from conftest import Recorder, tree

from sweep import cli

HIDDEN = ("code/", "old-clean", "scratch-app", "live-app", "installer.dmg", "old-folder", "old-build")


def plan(capsys, mac, *flags, judge=None):
    assert cli.main(["--json", *flags], ctx=mac, judge=judge or Recorder("safe")) == 0
    return json.loads(capsys.readouterr().out)


def test_redacted_json_hides_names_and_keeps_numbers(mac, capsys):
    plain, red = plan(capsys, mac), plan(capsys, mac, "--redact")
    text = json.dumps(red["items"])
    assert not any(name in text for name in HIDDEN)
    paths = [i["path"] for i in red["items"]]
    assert "~/Library/Caches/pip" in paths and "~/.npm/_cacache" in paths  # tool-owned places stay readable
    assert any(p.startswith("~/<dir>/<project-") and p.endswith("/node_modules") for p in paths)
    assert any(p.startswith("~/Downloads/<item-") for p in paths)
    assert any(p.startswith("$TMPDIR/<scratch-") for p in paths)
    keep = ("found_bytes", "safe_bytes", "ask_bytes", "keep_bytes", "counts")
    assert {k: red[k] for k in keep} == {k: plain[k] for k in keep}
    assert [(i["bytes"], i["verdict"]) for i in red["items"]] == [
        (i["bytes"], i["verdict"]) for i in plain["items"]
    ]
    assert "redacted" in red and "redacted" not in plain


def test_a_name_the_model_repeats_is_removed_from_its_reason(mac, capsys):
    def echo(batch):
        return {m["id"]: {"verdict": "safe", "reason": f"{m['name']} looks regenerable"} for m in batch}

    plain = json.dumps(plan(capsys, mac, judge=echo)["items"])
    red = json.dumps(plan(capsys, mac, "--redact", judge=echo)["items"])
    assert "scratch-app" in plain and "installer.dmg" in plain
    assert not any(name in red for name in HIDDEN) and "<name>" in red


def test_redacted_table_hides_names_and_deletes_nothing(mac, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "250")
    before = tree(tmp_path)
    assert cli.main(["--redact", "--top", "100"], ctx=mac, judge=Recorder("safe")) == 0
    out = capsys.readouterr().out
    assert not any(name in out for name in HIDDEN)
    assert "<project-" in out and "~/Library/Caches/pip" in out and "--redact:" in out
    assert tree(tmp_path) == before


def test_redact_refuses_apply(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--apply", "--redact"])
    assert e.value.code == 2 and "real paths" in capsys.readouterr().err
