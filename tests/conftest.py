"""A fake Mac home under tmp_path. Every test that deletes, deletes only inside it."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from sweep import model, scan
from sweep.scan import Context

DAY = 86400


@pytest.fixture(autouse=True)
def no_real_model_no_real_home(monkeypatch, tmp_path):
    """Tests never reach OpenRouter (no key anywhere) and never build a Context on the real home."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(model, "CREDENTIALS", tmp_path / "no-credentials.json")

    def refuse(*a, **k):
        raise AssertionError("a test tried to scan the real home folder")

    monkeypatch.setattr(scan.Context, "default", classmethod(refuse))


def write(p: Path, text: str = "x" * 4096) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def age(p: Path, days: float) -> None:
    """Set mtime of p and everything under it to `days` ago."""
    t = time.time() - days * DAY
    for dirpath, _, files in os.walk(p):
        for f in files:
            os.utime(os.path.join(dirpath, f), (t, t))
        os.utime(dirpath, (t, t))
    os.utime(p, (t, t))


def git_repo(path: Path, commit_days_ago: float, dirty: bool = False) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - commit_days_ago * DAY))
    env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
    write(path / ".gitignore", "node_modules/\n")
    write(path / "package.json", "{}")
    write(path / "package-lock.json", "{}")
    write(path / "src/index.js", "console.log(1)")

    def git(*a):
        subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "-c",
                "commit.gpgsign=false",
                *a,
            ],
            check=True,
            capture_output=True,
            env=env,
        )

    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    if dirty:
        write(path / "src/index.js", "console.log(2)  // not committed")
    write(path / "node_modules/pkg/index.js")


@pytest.fixture
def mac(tmp_path) -> Context:
    home, tmp, outside = tmp_path / "home", tmp_path / "tmp", tmp_path / "outside"
    write(home / "Library/Caches/pip/http/blob")
    write(home / "Library/Caches/com.example.app/cache.db")
    write(home / ".npm/_cacache/index")
    write(home / "Downloads/installer.dmg")
    write(home / "Downloads/old-folder/a.zip")
    write(home / ".Trash/old.txt")
    write(home / "Documents/notes.txt", "my notes")
    write(home / "Desktop/node_modules/keep.js")  # not under the roots
    git_repo(home / "code/old-clean", commit_days_ago=60)
    git_repo(home / "code/dirty", commit_days_ago=60, dirty=True)
    git_repo(home / "code/recent", commit_days_ago=2)
    write(home / "code/nomarker/target/data.bin")  # no Cargo.toml / pom.xml next to it
    write(home / "code/rust/Cargo.toml", "[package]")
    write(home / "code/rust/target/CACHEDIR.TAG", "Signature: 8a477f597d28d172789f06886806bc55")
    write(home / "code/rust/target/debug/app")
    write(home / "code/maven-data/pom.xml", "<project/>")
    write(home / "code/maven-data/target/my-results.csv")  # named target, but not build output
    write(home / "code/scratch-app/package.json", "{}")  # no git, no lockfile
    write(home / "code/scratch-app/node_modules/pkg/index.js")
    write(home / "code/live-app/package.json", "{}")
    write(home / "code/live-app/yarn.lock", "")
    write(home / "code/live-app/app.js", "edited today")  # no git, edited today
    write(home / "code/live-app/node_modules/pkg/index.js")
    write(home / "code/py/pyproject.toml", "[project]")
    write(home / "code/py/.venv/pyvenv.cfg", "home = /usr/bin")
    write(home / "code/py/.venv/lib/site.py")
    write(outside / "proj/package.json", "{}")
    write(outside / "proj/node_modules/pkg/index.js")
    write(outside / "precious/thesis.txt", "do not delete")
    (home / "code/linky").mkdir(parents=True)
    write(home / "code/linky/package.json", "{}")
    os.symlink(outside / "precious", home / "code/linky/node_modules")
    write(tmp / "old-build/out.o")
    age(tmp / "old-build", 3)
    write(tmp / "fresh/socket.lock")
    for p in (
        home / "Library",
        home / ".npm",
        home / "Downloads",
        home / "code/nomarker",
        home / "code/py",
        home / "code/rust",
        home / "code/maven-data",
        home / "code/scratch-app",
    ):
        age(p, 40)
    return Context(
        home=home,
        tmpdir=tmp,
        roots=(home / "code",),
        min_bytes=0,
        state_dir=tmp_path / "state",
        docker_probe=lambda: (5_000_000_000, "reclaimable per `docker system df`"),
    )


def tree(root: Path) -> set[str]:
    out = set()
    for dirpath, _, files in os.walk(root):
        for f in files:
            out.add(os.path.relpath(os.path.join(dirpath, f), root))
    return out


class Recorder:
    """A stub judge (test-only): answers `verdict` for every id and remembers what it was shown."""

    def __init__(self, verdict: str = "safe"):
        self.verdict, self.seen = verdict, []

    def __call__(self, batch: list[dict]) -> dict:
        self.seen.extend(batch)
        return {m["id"]: {"verdict": self.verdict, "reason": f"stub says {self.verdict}"} for m in batch}
