"""Every location sweep knows about, in one place.

macOS only for now. Adding Linux or Windows means adding a list here — a single pull request.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    path: str  # relative to $HOME
    kind: str  # browser-cache | package-cache | build-cache | simulator-data | trash | downloads | ...


MACOS_LOCATIONS: tuple[Location, ...] = (
    Location("Library/Caches/Google", "browser-cache"),
    Location("Library/Caches/com.apple.Safari", "browser-cache"),
    Location("Library/Caches/Firefox", "browser-cache"),
    Location("Library/Caches/pip", "package-cache"),
    Location("Library/Caches/Homebrew", "package-cache"),
    Location("Library/Caches/Yarn", "package-cache"),
    Location("Library/Caches/ms-playwright", "browser-binaries"),
    Location(".npm", "package-cache"),
    Location("Library/pnpm", "package-cache"),
    Location(".bun/install/cache", "package-cache"),
    Location(".cargo/registry", "package-cache"),
    Location(".gradle/caches", "build-cache"),
    Location("Library/Developer/Xcode/DerivedData", "build-cache"),
    Location("Library/Developer/CoreSimulator", "simulator-data"),
    Location(".Trash", "trash"),
    Location("Downloads", "downloads"),
)

# Folder names that a package manager or build tool can always regenerate.
REGENERABLE_DIRS: frozenset[str] = frozenset(
    {"node_modules", ".next", ".venv", "venv", "target", ".turbo", "__pycache__"}
)
