import pytest

from sweep import catalogue, cli


def test_default_run_exits_zero(capsys):
    assert cli.main([]) == 0


def test_version_names_the_model(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert "gemma" in capsys.readouterr().out


def test_catalogue_paths_are_relative_and_unique():
    paths = [loc.path for loc in catalogue.MACOS_LOCATIONS]
    assert len(paths) == len(set(paths))
    assert all(not p.startswith("/") for p in paths)
