"""Every location sweep knows about, in one place.

macOS only for now. Adding Linux or Windows means adding a list here — a single pull request.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    path: str  # relative to $HOME
    kind: str  # browser-cache | package-cache | build-cache | simulator-data | trash | downloads | ...
    expand: bool = False  # True: each child is its own item (the folder itself is never deleted)


MACOS_LOCATIONS: tuple[Location, ...] = (
    Location("Library/Caches/Google", "browser-cache"),
    Location("Library/Caches/com.apple.Safari", "browser-cache"),
    Location("Library/Caches/Firefox", "browser-cache"),
    Location("Library/Caches/BraveSoftware", "browser-cache"),
    Location("Library/Caches/pip", "package-cache"),
    Location("Library/Caches/Homebrew", "package-cache"),
    Location("Library/Caches/Yarn", "package-cache"),
    Location("Library/Caches/pnpm", "package-cache"),
    Location("Library/Caches/ms-playwright", "browser-binaries"),
    Location(".npm/_cacache", "package-cache"),
    Location("Library/pnpm/store", "package-cache"),
    Location(".bun/install/cache", "package-cache"),
    Location(".cargo/registry", "package-cache"),
    Location(".gradle/caches", "build-cache"),
    Location("Library/Developer/Xcode/DerivedData", "build-cache"),
    Location("Library/Developer/CoreSimulator", "simulator-data"),
    Location(".Trash", "trash"),
    Location("Library/Caches", "app-cache", expand=True),
    Location("Downloads", "downloads", expand=True),
)

# $TMPDIR is not under $HOME on macOS (/var/folders/...); each entry is its own item.
TMPDIR_KIND = "temp"

# Kinds the rules never let become SAFE automatically: a human decides.
ASK_AT_MOST_KINDS: frozenset[str] = frozenset({"downloads", "trash", "simulator-data"})

# Folder names that a package manager or build tool can regenerate — but only when the file that
# regenerates them sits next to them. No marker → the rules cap the item at ASK.
REGENERABLE_DIRS: dict[str, tuple[str, ...]] = {
    "node_modules": ("package.json",),
    ".next": ("package.json",),
    ".turbo": ("package.json", "turbo.json"),
    ".venv": ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "uv.lock"),
    "venv": ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "uv.lock"),
    "target": ("Cargo.toml", "pom.xml"),
    "__pycache__": (),  # Python rewrites these on the next import
}

# Never descended into when looking for project folders under a root (relative to $HOME).
WALK_PRUNE: frozenset[str] = frozenset({"Library", "Applications", "Pictures", "Music", "Movies"})

DOCKER_PRUNE_CMD = "docker system prune"
