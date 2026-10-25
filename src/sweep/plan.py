"""Step 3 — judgement. Rules first; the model only sees what the rules leave open, and only metadata.

Merge rule: the final verdict is the MORE cautious of (rule cap, model verdict). A missing or invalid
model answer counts as "ask". So the model can only ever make an item more cautious, never less.
"""

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from . import model, rules
from .scan import DAY, Context, Item

BATCH = 10
FALLBACK_REASON = "the model gave no valid answer, so sweep asks you"

Judge = Callable[[list[dict]], dict[str, dict]]


def display_path(it: Item, ctx: Context) -> str:
    if it.source == "docker":
        return "Docker (images, containers, build cache)"
    tmp, home = os.path.realpath(ctx.tmpdir), os.path.realpath(ctx.home)
    real = os.path.join(os.path.realpath(os.path.dirname(it.path)), os.path.basename(it.path))
    if real.startswith(tmp + "/"):
        return "$TMPDIR/" + real[len(tmp) + 1 :]
    if real.startswith(home + "/"):
        return "~/" + real[len(home) + 1 :]
    return real


def metadata(it: Item, ctx: Context) -> dict:
    """What the model sees. Names, sizes and ages only — never file contents, never the full path."""
    if it.source == "project":
        parts = display_path(it, ctx).split("/")
        name = "/".join(parts[-2:])
    else:
        name = display_path(it, ctx)
    md: dict = {"id": it.id, "name": name, "kind": it.kind, "size_mb": round((it.size or 0) / 1024 / 1024)}
    if it.mtime is not None:
        md["age_days"] = round((ctx.now - it.mtime) / DAY, 1)
    if it.source == "project":
        md["repo_last_commit_days"] = (
            round((ctx.now - it.repo_last_commit) / DAY, 1) if it.repo_last_commit is not None else None
        )
        md["in_git_repo"] = it.repo is not None
        md["repo_dirty"] = it.repo_dirty
    return md


def classify(items: list[Item], ctx: Context, judge: Judge = model.judge, workers: int = 4) -> list[Item]:
    open_items: list[tuple[Item, rules.Rule]] = []
    for it in items:
        r = rules.evaluate(it, ctx)
        if r.final:
            it.verdict, it.reason, it.decided_by = r.final, r.reason, "rule"
        else:
            open_items.append((it, r))

    batches = [open_items[i : i + BATCH] for i in range(0, len(open_items), BATCH)]

    def run(batch):
        try:
            return judge([metadata(it, ctx) for it, _ in batch])
        except Exception:  # noqa: BLE001 — any judge failure degrades to ASK, never crashes
            return {}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        answers = list(pool.map(run, batches))

    for batch, got in zip(batches, answers, strict=True):
        for it, r in batch:
            v = got.get(it.id) if isinstance(got, dict) else None
            ok = (
                isinstance(v, dict) and v.get("verdict") in rules.CAUTION and isinstance(v.get("reason"), str)
            )
            mv, mreason = (v["verdict"], v["reason"]) if ok else ("ask", FALLBACK_REASON)
            final = rules.more_cautious(r.cap, mv)
            if final == mv:
                it.verdict, it.reason, it.decided_by = final, mreason, "model" if ok else "fallback"
            else:
                it.verdict, it.reason, it.decided_by = final, r.reason, "rule"
    return items
