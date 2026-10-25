"""Step 1 — scan. Plain code, metadata only: path, kind, size, last-modified, repo activity.

Nothing here reads file contents or deletes anything.
"""

import dataclasses
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import catalogue

DAY = 86400.0
RECENT_DAYS = 14  # a project touched this recently is active


@dataclass
class Context:
    home: Path
    tmpdir: Path | None  # None → $TMPDIR is not scanned
    roots: tuple[Path, ...]
    min_bytes: int = 100 * 1024 * 1024
    state_dir: Path | None = None  # where last-run.json goes; default ~/.sweep
    docker_probe: Callable[[], tuple[int | None, str]] | None = None  # None → no Docker check
    now: float = field(default_factory=time.time)

    @classmethod
    def default(cls, roots: list[str] | None = None, min_mb: float = 100) -> "Context":
        home = Path(os.path.realpath(Path.home()))
        return cls(
            home=home,
            tmpdir=safe_tmpdir(os.environ.get("TMPDIR") or tempfile.gettempdir(), home),
            roots=validate_roots(roots or ["~"], home),
            min_bytes=int(min_mb * 1024 * 1024),
            state_dir=home / ".sweep",
            docker_probe=docker_df,
        )


_TMPDIR_SHAPES = (
    re.compile(r"/private/var/folders/[^/]+/[^/]+/T"),  # macOS per-user temp (what $TMPDIR normally is)
    re.compile(r"/private/tmp/[^/]+"),  # a private folder under /tmp, never /tmp itself
)


def safe_tmpdir(raw: str, home: Path) -> Path | None:
    """The real $TMPDIR, only if it has the exact shape of a per-user temp folder. Otherwise: not scanned."""
    real = os.path.realpath(raw).rstrip("/")
    home_s = os.path.realpath(home)
    if not any(shape.fullmatch(real) for shape in _TMPDIR_SHAPES) or home_s.startswith(real + "/"):
        return None
    return Path(real)


def validate_roots(roots: list[str], home: Path) -> tuple[Path, ...]:
    """--root must be your home folder or inside it, and never inside ~/Library."""
    home_s = os.path.realpath(home)
    out = []
    for r in roots:
        real = os.path.realpath(os.path.expanduser(r))
        inside = real == home_s or real.startswith(home_s + "/")
        lib = os.path.join(home_s, "Library")
        if not inside or real == lib or real.startswith(lib + "/"):
            raise ValueError(f"--root {r} must be your home folder or a folder inside it (not ~/Library)")
        out.append(Path(real))
    return tuple(out)


@dataclass
class Item:
    id: str
    path: str  # absolute filesystem path; "docker" for the Docker pseudo-item
    kind: str
    source: str  # catalogue | temp | project | docker
    size: int | None  # bytes on disk; None = unreadable
    mtime: float | None = None
    partial: bool = False  # some files inside could not be read
    note: str = ""
    repo: str | None = None
    repo_last_commit: float | None = None
    repo_dirty: bool | None = None
    marker_ok: bool | None = None  # project folders: the file that regenerates it is present
    recent_activity: bool | None = None  # temp entries: anything modified in the last 24 h
    verdict: str = ""
    reason: str = ""
    decided_by: str = ""  # rule | model | fallback


def _unreadable(p: Path) -> bool:
    try:
        if p.is_dir() and not p.is_symlink():
            os.listdir(p)
        return False
    except OSError:
        return True


def _du_chunk(paths: list[str]) -> dict[str, tuple[int | None, bool]]:
    try:
        r = subprocess.run(
            ["du", "-sk", *paths], capture_output=True, text=True, errors="replace", timeout=900
        )
    except (OSError, subprocess.TimeoutExpired):
        return {p: (None, False) for p in paths}
    out: dict[str, tuple[int | None, bool]] = {}
    for line in r.stdout.splitlines():
        kb, _, path = line.partition("\t")
        if kb.strip().isdigit():
            out[path] = (int(kb) * 1024, False)
    for line in r.stderr.splitlines():  # "du: <path>/sub: Permission denied" → that item is partial
        for p in paths:
            if line.startswith(f"du: {p}/") or line.startswith(f"du: {p}:"):
                size = out.get(p, (None, False))[0]
                out[p] = (size, True)
    return out


def du_many(paths: list[Path], chunk: int = 1, workers: int = 8) -> dict[Path, tuple[int | None, bool]]:
    """{path: (bytes on disk, partial)} — size None when the folder itself cannot be listed.

    Regular files are measured with lstat; folders with `du -sk`, one process per folder by default, so a
    hard-linked file is counted in every folder that links it (what `du -sh <folder>` shows). Deleting
    such a folder frees less; apply reports the measured free-space change too.
    """
    result: dict[Path, tuple[int | None, bool]] = {}
    dirs: list[str] = []
    for p in paths:
        try:
            st = p.lstat()
        except OSError:
            result[p] = (None, False)
            continue
        if stat.S_ISDIR(st.st_mode):
            if _unreadable(p):
                result[p] = (None, False)
            else:
                dirs.append(str(p))
        else:
            result[p] = (st.st_blocks * 512, False)
    chunks = [dirs[i : i + chunk] for i in range(0, len(dirs), chunk)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for got in pool.map(_du_chunk, chunks):
            for k, v in got.items():
                result[Path(k)] = v
    for d in dirs:
        result.setdefault(Path(d), (None, False))
    return result


def du_bytes(p: Path) -> tuple[int | None, bool]:
    return du_many([p])[p]


def newest_within(p: Path, since: float) -> bool:
    """True if p or anything under it was modified after `since` (stops at the first hit)."""
    try:
        if p.lstat().st_mtime > since:
            return True
        if not p.is_dir() or p.is_symlink():
            return False
        for dirpath, dirnames, filenames in os.walk(p, onerror=lambda e: None):
            for n in dirnames + filenames:
                try:
                    if os.lstat(os.path.join(dirpath, n)).st_mtime > since:
                        return True
                except OSError:
                    return True  # cannot tell → assume in use
    except OSError:
        return True
    return False


def _git(repo: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace", timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def repo_meta(folder: Path, cache: dict) -> tuple[str | None, float | None, bool | None]:
    """(repo top, last commit unix time, dirty) for the repo containing folder's parent.

    Not in a repo → (None, None, None). Git errors → dirty=None (the rules then refuse SAFE).
    """
    parent = folder.parent
    top = _git(parent, "rev-parse", "--show-toplevel")
    if top is None:
        # Not a repo — unless git itself failed: a .git above us means "state unknown".
        for a in (parent, *parent.parents):
            if (a / ".git").exists():
                return str(a), None, None
        return None, None, None
    top = top.strip()
    if top in cache:
        return cache[top]
    ts = _git(Path(top), "log", "-1", "--format=%ct")
    status = _git(Path(top), "status", "--porcelain")
    last = float(ts.strip()) if ts and ts.strip() else None
    dirty = None if status is None else bool(status.strip())
    cache[top] = (top, last, dirty)
    return cache[top]


def find_project_dirs(root: Path, skip: set[Path], max_depth: int = 12):
    """Yield regenerable folders under root. Never follows symlinks, skips hidden and system dirs."""
    stack = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            try:
                if not e.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            p = Path(e.path)
            if e.name in catalogue.REGENERABLE_DIRS:
                yield p
                continue  # never look inside a regenerable folder
            if e.name.startswith(".") or p in skip or depth + 1 > max_depth:
                continue
            stack.append((p, depth + 1))


def regenerable_ok(d: Path, roots: tuple[Path, ...] = ()) -> bool:
    """Does the thing that rebuilds this folder actually sit next to it?

    Lockfiles may sit up to 3 folders higher (monorepo workspaces), but never above the scan root.
    """
    spec = catalogue.REGENERABLE_DIRS[d.name]
    if spec.beside and not any((d.parent / m).exists() for m in spec.beside):
        return False
    if spec.above:
        top = [os.path.realpath(r) for r in roots]
        ups = [
            u
            for u in [d.parent, *list(d.parent.parents)[:3]]
            if not top
            or any(os.path.realpath(u) == t or os.path.realpath(u).startswith(t + "/") for t in top)
        ]
        if not any((u / m).exists() for u in ups for m in spec.above):
            return False
    return not spec.inside or any((d / m).exists() for m in spec.inside)


def project_recent(project: Path, since: float, limit: int = 20000) -> bool:
    """For a project outside git: was any of its own files (not regenerable folders) touched after `since`?

    Walks at most `limit` entries; a bigger tree counts as recent (cautious).
    """
    seen = 0
    for dirpath, dirnames, filenames in os.walk(project, onerror=lambda e: None):
        dirnames[:] = [n for n in dirnames if n not in catalogue.REGENERABLE_DIRS and not n.startswith(".")]
        for n in filenames:
            seen += 1
            if seen > limit:
                return True
            try:
                if os.lstat(os.path.join(dirpath, n)).st_mtime > since:
                    return True
            except OSError:
                return True
    return False


def refresh(it: "Item", ctx: Context) -> "Item":
    """Re-read the activity signals right before a delete (a repo may have changed since the scan)."""
    fresh = dataclasses.replace(it)
    p = Path(it.path)
    if fresh.source == "temp":
        fresh.recent_activity = newest_within(p, time.time() - DAY)
    elif fresh.source == "project":
        fresh.repo, fresh.repo_last_commit, fresh.repo_dirty = repo_meta(p, {})
        fresh.marker_ok = regenerable_ok(p, ctx.roots)
        if fresh.repo is None:
            fresh.recent_activity = project_recent(p.parent, time.time() - RECENT_DAYS * DAY)
    return fresh


def _mtime(p: Path) -> float | None:
    try:
        return p.lstat().st_mtime
    except OSError:
        return None


def scan(ctx: Context) -> list[Item]:
    found: list[tuple[Path, str, str, dict]] = []  # (path, kind, source, extra fields)
    items: list[Item] = []
    seen: set[Path] = set()

    # 1. Fixed catalogue (explicit locations first, so they win over the expanded parent).
    for loc in sorted(catalogue.MACOS_LOCATIONS, key=lambda loc: loc.expand):
        p = ctx.home / loc.path
        if not os.path.lexists(p) or p.is_symlink():
            continue
        if not loc.expand:
            seen.add(p)
            found.append((p, loc.kind, "catalogue", {}))
            continue
        try:
            children = sorted(os.scandir(p), key=lambda e: e.name)
        except OSError:
            found.append((p, loc.kind, "catalogue", {"note": "unreadable"}))
            continue
        for c in children:
            cp = Path(c.path)
            if cp in seen or c.is_symlink() or c.name == ".DS_Store":
                continue
            seen.add(cp)
            found.append((cp, loc.kind, "catalogue", {}))

    # 2. $TMPDIR entries.
    try:
        tmp_children = sorted(os.scandir(ctx.tmpdir), key=lambda e: e.name) if ctx.tmpdir else []
    except OSError:
        tmp_children = []
    for c in tmp_children:
        if not c.is_symlink():
            found.append((Path(c.path), catalogue.TMPDIR_KIND, "temp", {}))

    # 3. Regenerable project folders under the roots.
    skip = {ctx.home / name for name in catalogue.WALK_PRUNE} | seen | ({ctx.tmpdir} if ctx.tmpdir else set())
    for root in ctx.roots:
        for d in find_project_dirs(root, skip):
            if d in seen:
                continue
            seen.add(d)
            found.append((d, d.name, "project", {"marker_ok": regenerable_ok(d, ctx.roots)}))

    # Measure everything (one `du` per folder), then drop the small stuff.
    sizes = du_many([f[0] for f in found])
    git_cache: dict = {}
    for path, kind, source, extra in found:
        size, partial = sizes.get(path, (None, False))
        if size is not None and size < ctx.min_bytes:
            continue
        it = Item(
            id=f"i{len(items) + 1}",
            path=str(path),
            kind=kind,
            source=source,
            size=size,
            mtime=_mtime(path),
            partial=partial,
            **extra,
        )
        if source == "temp":  # anything touched in the last 24 h counts as in use
            it.recent_activity = newest_within(path, ctx.now - DAY)
        if source == "project":
            it.repo, it.repo_last_commit, it.repo_dirty = repo_meta(path, git_cache)
            if it.repo is None:  # no git history to go on: look at the project's own files instead
                it.recent_activity = project_recent(path.parent, ctx.now - RECENT_DAYS * DAY)
        items.append(it)

    # 4. Docker — measured with Docker's own tool, never deleted by sweep.
    if ctx.docker_probe:
        size, note = ctx.docker_probe()
        if size is not None or note:
            items.append(
                Item(
                    id=f"i{len(items) + 1}",
                    path="docker",
                    kind="docker",
                    source="docker",
                    size=size,
                    note=note,
                )
            )
    return items


_UNITS = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12}


def parse_docker_size(s: str) -> int:
    m = re.match(r"\s*([\d.]+)\s*([kKMGT]?B)", s)
    return int(float(m.group(1)) * _UNITS[m.group(2).upper()]) if m else 0


def docker_df() -> tuple[int | None, str]:
    """(reclaimable bytes, note). (None, "") when Docker is not installed."""
    if not shutil.which("docker"):
        return None, ""
    try:
        r = subprocess.run(
            ["docker", "system", "df", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "Docker did not answer"
    if r.returncode != 0:
        return None, "Docker is installed but not running"
    total = 0
    for line in r.stdout.splitlines():
        try:
            total += parse_docker_size(json.loads(line).get("Reclaimable", ""))
        except (ValueError, AttributeError):
            continue
    return total, "reclaimable per `docker system df`"
