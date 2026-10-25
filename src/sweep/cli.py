"""Command-line entry point. Default is a dry run; nothing is deleted without --apply and a typed OK."""

import argparse

from . import __version__
from .model import MODEL_ID


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sweep", description="Find the junk on your Mac. Deletes nothing by default."
    )
    p.add_argument("--apply", action="store_true", help="delete the SAFE items after a typed confirmation")
    p.add_argument("--json", action="store_true", help="print the plan as JSON")
    p.add_argument("--version", action="version", version=f"sweep {__version__} (model {MODEL_ID})")
    return p


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print("sweep: scanner not wired yet (scaffold)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
