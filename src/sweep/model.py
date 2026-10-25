"""The judgement step: a hosted open-weight model sees metadata only and returns strict JSON verdicts.

Any failure (no key, network error, timeout, bad JSON) returns no verdicts, and the caller treats
the item as ASK. The model never sees file contents.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

MODEL_ID = "google/gemma-4-31b-it"  # pinned; see evidence/model-spike.md
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
VERDICTS = ("safe", "ask", "keep")
CREDENTIALS = Path.home() / ".config/openrouter/credentials.json"

SYSTEM_PROMPT = """You are the judgement step of a cautious macOS disk-cleanup tool.
You receive ONLY metadata about candidate folders (never their contents). For every item decide:
- "safe": regenerable cache/build output; deleting it loses nothing the user cannot re-download or rebuild.
- "ask": probably deletable but the user should confirm
  (personal files, large or ambiguous items, things in use).
- "keep": should not be deleted now (active project, recent activity, uncommitted work).
When unsure, choose the more cautious verdict.
Reply with JSON only, exactly this shape, one entry per input id, no extra keys:
{"items":[{"id":"<input id>","verdict":"safe|ask|keep","reason":"<one short plain-English sentence>"}]}"""


def api_key() -> str | None:
    """OPENROUTER_API_KEY, else the first key in ~/.config/openrouter/credentials.json."""
    if key := os.environ.get("OPENROUTER_API_KEY"):
        return key
    try:
        return json.loads(CREDENTIALS.read_text())["keys"][0]["key"]
    except (OSError, KeyError, IndexError, TypeError, ValueError):
        return None


def parse_verdicts(content: str | None, ids: set[str]) -> dict[str, dict]:
    """Validate the strict contract; return {id: {"verdict", "reason"}} for entries that pass."""
    if not content:
        return {}
    try:
        obj = json.loads(content.strip())
    except json.JSONDecodeError:
        return {}
    entries = obj.get("items") if isinstance(obj, dict) else None
    if not isinstance(entries, list):
        return {}
    good: dict[str, dict] = {}
    for e in entries:
        if not isinstance(e, dict) or set(e) != {"id", "verdict", "reason"}:
            continue
        if not isinstance(e["id"], str) or e["id"] not in ids or e["id"] in good:
            continue
        reason = e["reason"]
        if e["verdict"] in VERDICTS and isinstance(reason, str) and 0 < len(reason) <= 200:
            good[e["id"]] = {"verdict": e["verdict"], "reason": reason}
    return good


def judge(items: list[dict], model: str = MODEL_ID, timeout: float = 90.0) -> dict[str, dict]:
    """Ask the model about one batch of metadata dicts (each with an "id"). Never raises."""
    key = api_key()
    if not key or not items:
        return {}
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"items": items})},
        ],
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "sweep"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"].get("content")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        return {}
    return parse_verdicts(content, {i["id"] for i in items})
