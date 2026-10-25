"""Step 2 — hard rules. Plain code; the model can never override them.

`evaluate` returns either a final verdict (the model is not asked) or a cap: the least cautious
verdict the model is allowed to give. `allowed_path` is checked at plan time AND again right
before anything is deleted.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from . import catalogue
from .scan import DAY, RECENT_DAYS, Context, Item

CAUTION = {"safe": 0, "ask": 1, "keep": 2}

# Never deleted, never a parent of something deleted from the catalogue side.
PROTECTED = (
    "/",
    "/System",
    "/Library",
    "/Applications",
    "/usr",
    "/bin",
    "/sbin",
    "/etc",
    "/private/etc",
    "/opt",
    "/Volumes",
    "/cores",
)
PROTECTED_HOME = (
    "Documents",
    "Desktop",
    "Pictures",
    "Movies",
    "Music",
    "Library",
    "Downloads",
    ".ssh",
    ".config",
    ".sweep",
)


@dataclass(frozen=True)
class Rule:
    final: str | None  # set → this is the verdict, the model is not consulted
    cap: str  # otherwise: the model may answer this or anything more cautious
    reason: str


def more_cautious(a: str, b: str) -> str:
    return a if CAUTION[a] >= CAUTION[b] else b


def _inside(path: str, parent: Path) -> bool:
    """True if path is strictly inside parent (no symlink games: compare real parents)."""
    real = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
    parent_s = os.path.realpath(parent)
    return real != parent_s and real.startswith(parent_s.rstrip("/") + "/")


def allowed_path(it: Item, ctx: Context) -> bool:
    """Is this a location sweep is ever allowed to delete? (Catalogue or regenerable, inside the roots.)"""
    if it.source == "docker" or not it.path.startswith("/") or os.path.islink(it.path):
        return False
    real = os.path.join(os.path.realpath(os.path.dirname(it.path)), os.path.basename(it.path))
    home = os.path.realpath(ctx.home)
    if real in PROTECTED or real == home or real in {os.path.join(home, p) for p in PROTECTED_HOME}:
        return False
    if any(real.startswith(p + "/") for p in PROTECTED if p != "/"):  # inside a system folder
        return False
    if any(real == os.path.realpath(r) for r in ctx.roots):
        return False
    if it.source == "temp":
        if not ctx.tmpdir:
            return False
        tmp = os.path.realpath(ctx.tmpdir)
        if tmp == "/" or home.startswith(tmp + "/") or tmp.startswith(home + "/") or tmp == home:
            return False
        return os.path.dirname(real) == tmp
    if it.source == "catalogue":
        for loc in catalogue.MACOS_LOCATIONS:
            base = os.path.join(home, loc.path)
            if loc.expand and os.path.dirname(real) == base:
                return True
            if not loc.expand and real == base:
                return True
        return False
    if it.source == "project":
        regenerable = os.path.basename(real) in catalogue.REGENERABLE_DIRS
        return regenerable and any(_inside(real, r) for r in ctx.roots)
    return False


def evaluate(it: Item, ctx: Context) -> Rule:
    if it.source == "docker":
        why = f"never deleted by sweep — review, then run `{catalogue.DOCKER_PRUNE_CMD}`"
        return Rule("ask", "ask", why + (f" ({it.note})" if it.size is None and it.note else ""))
    if it.size is None:
        return Rule("ask", "ask", "unreadable (macOS privacy protection; needs Full Disk Access)")
    if not allowed_path(it, ctx):
        return Rule("keep", "keep", "outside the locations sweep is allowed to touch")
    if it.source == "project":
        if it.repo_dirty:
            return Rule("keep", "keep", "its repo has uncommitted changes")
        last = it.repo_last_commit
        if last is not None and ctx.now - last < RECENT_DAYS * DAY:
            days = max(0, int((ctx.now - last) // DAY))
            return Rule("keep", "keep", f"its repo had a commit {days} days ago (active project)")
        if it.repo is None and it.recent_activity:
            return Rule(
                "keep", "keep", f"its project files changed in the last {RECENT_DAYS} days (no git repo)"
            )
        if it.repo is not None and it.repo_dirty is None:
            return Rule(None, "ask", "could not read its git status")
        if not it.marker_ok:
            return Rule(
                None,
                "ask",
                "nothing next to it can regenerate it (no manifest/lockfile, or not build output)",
            )
    if it.source == "temp" and it.recent_activity:
        return Rule("keep", "keep", "modified in the last 24 hours (probably in use)")
    if it.partial:
        return Rule(None, "ask", "some files inside could not be read")
    if it.kind in catalogue.ASK_AT_MOST_KINDS:
        return Rule(None, "ask", f"{it.kind} is never deleted without asking")
    return Rule(None, "safe", "")
