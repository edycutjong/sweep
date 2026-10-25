"""Step 4b — apply. Deletes only SAFE items, only after a typed confirmation, and logs every path."""

import json
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from . import catalogue, rules
from .model import MODEL_ID
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


def apply(
    items: list[Item], ctx: Context, ask: Callable[[str], str] = input, say: Callable[[str], None] = print
) -> dict:
    targets = deletable(items, ctx)
    if not targets:
        say("Nothing is SAFE to delete. Nothing was removed.")
        return {"removed": [], "failed": [], "freed_bytes": 0, "confirmed": False}
    phrase = confirm_phrase(targets)
    try:
        answer = ask(f'Type "{phrase}" to remove {len(targets)} SAFE items (anything else cancels): ')
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip() != phrase:
        say("Cancelled. Nothing was removed.")
        return {"removed": [], "failed": [], "freed_bytes": 0, "confirmed": False}

    removed, failed = [], []
    for it in targets:
        if not rules.allowed_path(it, ctx):  # re-check right before deleting
            failed.append({"path": it.path, "error": "failed the path guard"})
            continue
        try:
            st = os.lstat(it.path)
            if os.path.islink(it.path):
                raise OSError("is a symlink")
            if os.path.isdir(it.path):
                shutil.rmtree(it.path)
            else:
                os.unlink(it.path)
            removed.append({"path": it.path, "bytes": it.size, "mtime": st.st_mtime})
        except OSError as e:
            failed.append({"path": it.path, "error": str(e)})
    freed = sum(r["bytes"] for r in removed)
    log = {
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": MODEL_ID,
        "removed": removed,
        "failed": failed,
        "freed_bytes": freed,
        "confirmed": True,
    }
    state = Path(ctx.state_dir or ctx.home / ".sweep")
    state.mkdir(parents=True, exist_ok=True)
    (state / "last-run.json").write_text(json.dumps(log, indent=2) + "\n")
    say(f"freed {gb(freed)} · {len(removed)} removed · {len(failed)} failed · log: {state / 'last-run.json'}")
    return log
