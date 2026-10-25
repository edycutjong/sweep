"""--redact: hide the names you chose (projects, folders, files) so a plan can be shared as a screenshot."""

import re

from .plan import display_path
from .scan import Context, Item

KNOWN_TMP = ("node-compile-cache", "TemporaryItems")  # names macOS and Node pick, not you
GENERIC = {"build", "app", "apps", "packages", "src", "web", "frontend", "backend", "server", "client", "api"}


class Names:
    """Paths and reasons as shown. With redact off this is display_path and the reason, unchanged.

    With redact on, tool-owned places stay readable (~/Library, ~/.dot-dirs, Docker, tmp.*) and the rest
    become ~/<dir>/<project-NNN>/<artifact>, ~/<top>/<item-NN> or $TMPDIR/<scratch-NN>, numbered by size
    like --json. The name the model saw (a project's folder, a file or scratch name) is also removed from that
    item's reason, since the model may repeat it. Sizes, verdicts and totals are never changed."""

    def __init__(self, items: list[Item], ctx: Context, redact: bool = False):
        self.ctx, self.on = ctx, redact
        self.paths: dict[str, str] = {}
        self.hidden: dict[str, list[str]] = {}
        if not redact:
            return
        n = {"project": 0, "item": 0, "scratch": 0}
        for it in sorted(items, key=lambda i: -(i.size or 0)):
            shown = display_path(it, ctx)
            segs = shown.split("/")
            if it.source == "project" and shown.startswith("~/") and len(segs) > 2:
                label, names = "project", segs[-2:-1]  # the model sees parent/artifact
                fmt = "~/<dir>/<project-{:03d}>/" + segs[-1]
            elif shown.startswith("$TMPDIR/") and not (segs[1].startswith("tmp.") or segs[1] in KNOWN_TMP):
                label, names, fmt = "scratch", segs[1:], "$TMPDIR/<scratch-{:02d}>"
            elif shown.startswith("~/") and not shown.startswith(("~/Library/", "~/.")) and len(segs) > 2:
                label, names = "item", segs[2:]
                fmt = f"~/{segs[1]}/<item-{{:02d}}>"
            else:
                continue
            n[label] += 1
            self.paths[it.id] = fmt.format(n[label])
            self.hidden[it.id] = [s for s in names if len(s) > 3 and s.lower() not in GENERIC]

    def path(self, it: Item) -> str:
        return self.paths.get(it.id) or display_path(it, self.ctx)

    def reason(self, it: Item) -> str:
        text = it.reason
        for name in sorted(self.hidden.get(it.id, ()), key=len, reverse=True):
            text = re.sub(re.escape(name), "<name>", text, flags=re.IGNORECASE)
        return text
