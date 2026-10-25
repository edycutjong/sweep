"""Step 4a — the plan: SAFE / ASK / KEEP, with reasons, and a footer you can quote."""

import time

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .apply import gb
from .plan import display_path
from .scan import Context, Item

GROUPS = (("safe", "SAFE", "green"), ("ask", "ASK", "yellow"), ("keep", "KEEP", "dim"))


def is_minor(it: Item) -> bool:
    """Unreadable children of ~/Library/Caches or $TMPDIR: one summary line here, all of them in --json."""
    return it.size is None and it.kind in ("app-cache", "temp")


def totals(items: list[Item]) -> dict:
    t = {v: sum(it.size or 0 for it in items if it.verdict == v) for v, _, _ in GROUPS}
    t["found"] = sum(it.size or 0 for it in items)
    return t


def to_json(items: list[Item], ctx: Context, seconds: float, model_id: str) -> dict:
    t = totals(items)
    return {
        "tool": "sweep",
        "model": model_id,
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scan_seconds": round(seconds, 1),
        "sizes": SIZES_NOTE,
        "found_bytes": t["found"],
        "safe_bytes": t["safe"],
        "ask_bytes": t["ask"],
        "keep_bytes": t["keep"],
        "counts": {v: sum(1 for it in items if it.verdict == v) for v, _, _ in GROUPS},
        "items": [
            {
                "path": display_path(it, ctx),
                "kind": it.kind,
                "bytes": it.size,
                "verdict": it.verdict,
                "reason": it.reason,
                "decided_by": it.decided_by,
            }
            for it in sorted(items, key=lambda i: -(i.size or 0))
        ],
    }


def footer(items: list[Item], seconds: float, model_id: str) -> str:
    t = totals(items)
    return (
        f"found {gb(t['found'])} · safe {gb(t['safe'])} (du) · scanned in {seconds:.0f} s · model {model_id}"
    )


SIZES_NOTE = (
    "sizes are du sizes; hard-linked files (pnpm, bun) are counted in every folder, so deleting frees less"
)


def render(
    items: list[Item],
    ctx: Context,
    seconds: float,
    model_id: str,
    top: int = 15,
    console: Console | None = None,
) -> None:
    c = console or Console()
    for verdict, title, style in GROUPS:
        group = sorted((it for it in items if it.verdict == verdict), key=lambda i: -(i.size or 0))
        if not group:
            continue
        size = sum(it.size or 0 for it in group)
        table = Table(
            title=f"[bold {style}]{title}[/] · {len(group)} items · {gb(size)}",
            title_justify="left",
            show_header=False,
            box=None,
            pad_edge=False,
            style=style,
        )
        table.add_column(justify="right", style=style, no_wrap=True)
        table.add_column(style=style, overflow="fold")
        table.add_column(style="italic" if verdict != "safe" else style, overflow="fold")
        minor = [it for it in group if is_minor(it)]
        shown = [it for it in group if not is_minor(it)]
        for it in shown[:top]:
            cell = gb(it.size) if it.size is not None else "unreadable"
            table.add_row(cell, Text(display_path(it, ctx)), Text(it.reason))  # Text: names are not markup
        if len(shown) > top:
            table.add_row("", f"… and {len(shown) - top} more (sweep --top {len(shown)})", "")
        if minor:
            table.add_row(
                "unreadable", f"{len(minor)} more system caches / temp entries", Text(minor[0].reason)
            )
        c.print(table)
        c.print()
    c.print(Text(footer(items, seconds, model_id), style="bold"))
    c.print(
        Text(
            f"dry run — nothing was deleted. {SIZES_NOTE}. `sweep --apply` removes only SAFE items.",
            style="dim",
        )
    )
