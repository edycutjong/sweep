"""Command-line entry point. Default is a dry run; nothing is deleted without --apply and a typed OK."""

import argparse
import json
import sys
import time
from collections.abc import Callable

from rich.console import Console

from . import __version__, model, plan, render, scan
from .apply import apply
from .model import MODEL_ID


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sweep", description="Find the junk on your Mac. Deletes nothing by default."
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="delete the SAFE items after a typed confirmation")
    mode.add_argument("--json", action="store_true", help="print the plan as JSON (never deletes)")
    p.add_argument(
        "--root",
        action="append",
        metavar="DIR",
        help="where to look for node_modules/.venv/target/... (repeatable, default ~)",
    )
    p.add_argument("--min-mb", type=float, default=100, help="ignore items smaller than this (default 100)")
    p.add_argument("--top", type=int, default=15, help="rows shown per group (default 15)")
    p.add_argument("--version", action="version", version=f"sweep {__version__} (model {MODEL_ID})")
    return p


def main(
    argv: list[str] | None = None,
    ctx: scan.Context | None = None,
    judge: plan.Judge | None = None,
    ask: Callable[[str], str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        ctx = ctx or scan.Context.default(args.root, args.min_mb)
    except ValueError as e:
        print(f"sweep: {e}", file=sys.stderr)
        return 2
    err = Console(stderr=True)
    t0 = time.monotonic()
    if not args.json:
        err.print("[dim]scanning (read-only)…[/]")
    items = scan.scan(ctx)
    if not args.json:
        err.print(f"[dim]{len(items)} candidates · asking {MODEL_ID} about the ones the rules leave open…[/]")
    plan.classify(items, ctx, judge or model.judge)
    seconds = time.monotonic() - t0

    if args.json:
        print(json.dumps(render.to_json(items, ctx, seconds, MODEL_ID), indent=2))
    else:
        render.render(items, ctx, seconds, MODEL_ID, top=args.top)
    if args.apply:
        if ask is None and not sys.stdin.isatty():
            print("--apply needs an interactive terminal for the typed confirmation. Nothing was removed.")
            return 1
        apply(items, ctx, ask=ask or input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
