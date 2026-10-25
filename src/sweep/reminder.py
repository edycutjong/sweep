"""Weekly reminder: a launchd plist running `sweep --notify` (dry run + one notification). Never deletes."""

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "dev.sweep.reminder"
DEFAULT_PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
WEEKLY = {"Weekday": 0, "Hour": 10, "Minute": 0}  # Sunday 10:00


def sweep_command() -> list[str]:
    exe = shutil.which("sweep")
    return [exe] if exe else [sys.executable, "-m", "sweep.cli"]


def plist_bytes(command: list[str] | None = None) -> bytes:
    """The launchd job: `sweep --notify` every Sunday at 10:00. No --apply anywhere."""
    job = {
        "Label": LABEL,
        "ProgramArguments": [*(command or sweep_command()), "--notify"],
        "StartCalendarInterval": WEEKLY,
        "StandardOutPath": str(Path.home() / ".sweep/reminder.log"),
        "StandardErrorPath": str(Path.home() / ".sweep/reminder.log"),
    }
    return plistlib.dumps(job)


def install(path: Path | None = None, command: list[str] | None = None) -> Path:
    """Write the plist and nothing else: loading it into launchd is left to the user."""
    path = Path(path) if path else DEFAULT_PLIST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plist_bytes(command))
    return path


def message(safe_bytes: int) -> str:
    return f"{safe_bytes / 1e9:.1f} GB (du) looks safe to clear: run sweep"


def notify(text: str) -> None:
    script = f'display notification {_applescript_string(text)} with title "sweep"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def _applescript_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
