"""Step 4b — apply. Deletes only SAFE items, only after a typed confirmation, and logs every path."""

import json
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from . import catalogue, rules, scan
from .model import MODEL_ID
from .plan import display_path
from .scan import Context, Item


def gb(n: int | None) -> str:
    return "?" if n is None else f"{n / 1e9:.1f} GB"


def deletable(items: list[Item], ctx: Context) -> list[Item]:
    """SAFE items that still pass every guard and every hard rule. Docker, Downloads, Trash never do."""
    out = []
    for it in items:
        if it.verdict != "safe" or it.size is None or it.source == "docker":
            continue
        if it.kind in catalogue.ASK_AT_MOST_KINDS or not rules.allowed_path(it, ctx):
            continue
        r = rules.evaluate(it, ctx)  # the hard rules again: a forged "safe" cannot get past them
        if r.final is not None or r.cap != "safe":
            continue
        out.append(it)
    return out


def confirm_phrase(items: list[Item]) -> str:
    return f"DELETE {gb(sum(it.size or 0 for it in items))}"


def free_bytes(path: Path) -> int | None:
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    return st.f_bavail * st.f_frsize


def still_safe(it: Item, ctx: Context) -> str | None:
    """Re-read git state / recent activity right before deleting. Returns why not, or None if still SAFE."""
    if os.path.islink(it.path) or not os.path.lexists(it.path):
        return "gone or replaced by a symlink since the scan"
    fresh = scan.refresh(it, ctx)
    if not rules.allowed_path(fresh, ctx):
        return "failed the path guard"
    r = rules.evaluate(fresh, ctx)
    if r.final is not None or r.cap != "safe":
        return f"no longer SAFE: {r.reason}"
    return None


def apply(
    items: list[Item], ctx: Context, ask: Callable[[str], str] = input, say: Callable[[str], None] = print
) -> dict:
    targets = deletable(items, ctx)
    if not targets:
        say("Nothing is SAFE to delete. Nothing was removed.")
        return {"removed": [], "failed": [], "freed_bytes": 0, "confirmed": False}
    say(f"These {len(targets)} SAFE items will be removed (nothing else):")
    for it in sorted(targets, key=lambda i: -(i.size or 0)):
        say(f"  {gb(it.size):>9}  {display_path(it, ctx)}")
    phrase = confirm_phrase(targets)
    try:
        answer = ask(
            f'Sizes are by du (hard-linked files free less). Type "{phrase}" to remove these '
            f"{len(targets)} items (anything else cancels): "
        )
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip() != phrase:
        say("Cancelled. Nothing was removed.")
        return {"removed": [], "failed": [], "freed_bytes": 0, "confirmed": False}

    free_before = free_bytes(ctx.home)
    removed: list[dict] = []
    failed: list[dict] = []
    try:
        for it in targets:
            why_not = still_safe(it, ctx)  # the plan may be minutes old: check again, item by item
            if why_not:
                failed.append({"path": it.path, "error": why_not})
                continue
            try:
                if os.path.isdir(it.path):
                    shutil.rmtree(it.path)
                else:
                    os.unlink(it.path)
                removed.append({"path": it.path, "bytes": it.size})
            except OSError as e:
                failed.append({"path": it.path, "error": str(e)})
    finally:  # even after Ctrl-C, the log records what is already gone
        log = write_log(ctx, removed, failed, free_before, say)
    return log


def write_log(ctx: Context, removed: list[dict], failed: list[dict], free_before: int | None, say) -> dict:
    free_after = free_bytes(ctx.home)
    du_total = sum(r["bytes"] for r in removed)
    measured = None if free_before is None or free_after is None else max(0, free_after - free_before)
    log = {
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": MODEL_ID,
        "removed": removed,
        "failed": failed,
        "freed_bytes": measured if measured is not None else du_total,  # what the disk really got back
        "removed_du_bytes": du_total,  # sum of du sizes: more than freed when files were hard-linked
        "free_space_before": free_before,
        "free_space_after": free_after,
        "confirmed": True,
    }
    state = Path(ctx.state_dir or ctx.home / ".sweep")
    try:
        state.mkdir(parents=True, exist_ok=True)
        (state / "last-run.json").write_text(json.dumps(log, indent=2) + "\n")
        where = f"log: {state / 'last-run.json'}"
    except OSError as e:
        where = f"could not write the log ({e})"
    if measured is not None:
        disk = f"disk free {gb(free_before)} → {gb(free_after)}"
        head = f"freed {gb(measured)} ({disk}; du of removed items {gb(du_total)})"
    else:
        head = f"removed {gb(du_total)} by du (free space not measurable)"
    say(f"{head} · {len(removed)} removed · {len(failed)} skipped · {where}")
    return log
