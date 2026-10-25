"""Command-line entry point. Default is a dry run; nothing is deleted without --apply and a typed OK."""

import argparse
import json
import sys
import time
from collections.abc import Callable

from rich.console import Console

from . import __version__, model, plan, reminder, render, scan
from .apply import apply
from .model import MODEL_ID


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sweep", description="Find the junk on your Mac. Deletes nothing by default."
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="delete the SAFE items after a typed confirmation")
    mode.add_argument("--json", action="store_true", help="print the plan as JSON (never deletes)")
    mode.add_argument("--notify", action="store_true", help="dry run, then one notification")
    mode.add_argument(
        "--install-reminder",
        nargs="?",
        const="",
        metavar="PLIST",
        help="write a weekly launchd job that runs --notify; does not load it",
    )
    p.add_argument(
        "--root",
        action="append",
        metavar="DIR",
        help="where to look for node_modules/.venv/target/... (repeatable, default ~)",
    )
    p.add_argument(
        "--redact",
        action="store_true",
        help="swap names under ~ for <project-NNN>/<item-NN> labels (~/Library, dot-dirs stay visible)",
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
    notifier: Callable[[str], None] = reminder.notify,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.redact and args.apply:
        parser.error("--redact is for sharing a dry-run plan; --apply always shows the real paths it deletes")
    if args.install_reminder is not None:
        path = reminder.install(args.install_reminder or None)
        print(f"wrote {path} (weekly dry run + notification, never deletes). Not loaded; to turn it on:")
        print(f"  launchctl bootstrap gui/$(id -u) {path}")
        return 0
    try:
        ctx = ctx or scan.Context.default(args.root, args.min_mb)
    except ValueError as e:
        print(f"sweep: {e}", file=sys.stderr)
        return 2
    err = Console(stderr=True)
    t0 = time.monotonic()
    quiet = args.json or args.notify
    if not quiet:
        err.print("[dim]scanning (read-only)…[/]")
    items = scan.scan(ctx)
    if not quiet:
        err.print(f"[dim]{len(items)} candidates · asking {MODEL_ID} about the ones the rules leave open…[/]")
    plan.classify(items, ctx, judge or model.judge)
    seconds = time.monotonic() - t0

    if args.notify:
        notifier(reminder.message(render.totals(items)["safe"]))
    elif args.json:
        print(json.dumps(render.to_json(items, ctx, seconds, MODEL_ID, redact=args.redact), indent=2))
    else:
        render.render(items, ctx, seconds, MODEL_ID, top=args.top, redact=args.redact)
    if args.apply:
        if ask is None and not sys.stdin.isatty():
            print("--apply needs an interactive terminal for the typed confirmation. Nothing was removed.")
            return 1
        apply(items, ctx, ask=ask or input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
