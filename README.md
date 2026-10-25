<div align="center">
  <h1>sweep 🧹</h1>
  <p><em>A lazy disk-cleanup agent for macOS. It finds the junk, asks an open-weight model what is safe, and never deletes without your typed OK.</em></p>

  <br/>

  [![Hacktoberfest AI Challenge](https://img.shields.io/badge/DEV-Hacktoberfest_AI_Challenge-8b5cf6?style=for-the-badge)](https://dev.to/devteam/join-the-hacktoberfest-open-source-ai-challenge-slow-and-steady-2850-in-prizes-across-21-3iee)
  [![Real dry run](https://img.shields.io/badge/📊_Real_Dry-Run-f59e0b?style=for-the-badge)](evidence/dry-run-2026-10-25.md)

  <br/>

  ![Python](https://img.shields.io/badge/Python_3.11+-3776AB?style=flat&logo=python&logoColor=white)
  ![Gemma](https://img.shields.io/badge/Gemma_4_31B-4285F4?style=flat&logo=google&logoColor=white)
  ![OpenRouter](https://img.shields.io/badge/OpenRouter-111111?style=flat)
  ![macOS](https://img.shields.io/badge/macOS_only-000000?style=flat&logo=apple&logoColor=white)
  [![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

</div>

---

> **macOS only for now — adding Linux or Windows is a small pull request, PRs welcome.** Every cache location lives in one file, [`src/sweep/catalogue.py`](src/sweep/catalogue.py); a port also touches `rules.py` (protected paths) and `reminder.py` (launchd).

## 📸 See it in Action

![sweep: a real dry run on a full Mac, from df to the SAFE / ASK / KEEP plan](docs/demo.gif)

<sub>A second real dry run on the same Mac, about 50 minutes after the evidence run below: `df -h ~`, then `sweep --redact --top 5` (`--redact` swaps the names under your home for labels like `<project-007>`). Most of the 3 min 17 s scan and of the 13 s of model calls are cut, and each cut is labelled. This run's numbers: [demo-run-2026-10-25.md](evidence/demo-run-2026-10-25.md).</sub>

`sweep` is a dry run by default. This is the real result on the author's own MacBook ([full report](evidence/dry-run-2026-10-25.md)):

| Measurement | Value |
|---|---|
| Items found | 167 |
| Found | 118.5 GB |
| SAFE (by `du`) | 45 items · 34.2 GB |
| ASK | 20 items · 33.6 GB |
| KEEP | 102 items · 50.7 GB |
| Judged by a hard rule / by the model | 111 / 56 |
| Wall time | 202.6 s |
| Model | `google/gemma-4-31b-it` |
| Deleted | nothing (dry run) |

Sizes are `du` sizes. Hard-linked files (pnpm, bun) are counted in every folder, so deleting frees less than the SAFE total. 34.2 GB is "safe to delete", not "freed".

## 💡 The Problem & Solution

### The Problem
A developer's Mac fills up with regenerable junk: `node_modules`, `.next`, Rust `target/`, `.venv`, package-manager caches, browser caches, temp files. Finding it is tedious, and a cleaner that guesses wrong deletes real work.

### The Solution
`sweep` splits the job in two. **Plain code** scans the machine and applies hard safety rules that the model can never override. **An open-weight model** judges only what the rules leave open (`safe`, `ask` or `keep`, with a one-line reason). The two verdicts are merged and the more cautious one wins. If the model fails or answers badly, the item becomes `ask`. Deleting is a separate, explicit step.

## 🏗️ Architecture & Tech Stack

```
scan.py ──► rules.py ──► plan.py ──► render.py  (rich table / --json)
 find        hard rules     model       │
 + size      (final or      judges      └─► apply.py  (--apply only: typed confirmation)
 + git       a cap)         the rest
```

| Layer | Choice |
|---|---|
| Language | Python 3.11+, packaged with `uv`, console script `sweep` |
| Model | `google/gemma-4-31b-it` via [OpenRouter](https://openrouter.ai), hosted, no local inference |
| Model client | stdlib `urllib`, strict JSON contract, temperature 0, batches of 10 |
| Output | `rich` plan table, or `--json` |
| Tests | `pytest`, `ruff` |

## 🏆 Gemma Integration

Gemma is the judge in the loop, not decoration. For every item the rules leave open, `sweep` sends the model the kind, size, age and git state of the item, and it must return `{"items":[{id, verdict, reason}]}`.

- **Strict contract.** Fenced output, extra keys or unknown ids are rejected, and the item becomes `ask`.
- **More-cautious-only merge.** The model can lower a rule's cap (`safe` → `ask` → `keep`), never raise it.
- **Why Gemma 4.** We ran five open-weight models over the same 20 real items, three runs each. All five returned valid JSON 20/20 times with zero unsafe SAFE verdicts (SAFE on Downloads, simulator data, or a dirty or recently committed project), so the tie-break was reason quality: Gemma 4 gave regenerability reasons. Table: [`evidence/model-spike.md`](evidence/model-spike.md).
- **Auditable.** `sweep --json` records `decided_by` per item: `rule` (a hard rule settled or capped it), `model`, or `fallback` (no valid model answer).

## 🛡️ Safety Rules

Code, not prompt. The model is not asked about an item that a rule already settled.

| Rule | Result |
|---|---|
| Docker images, containers and build cache | never deleted by `sweep`; it prints `docker system prune` for you to run |
| Unreadable folder (macOS privacy protection) | `ask` (shown as "unreadable"; contributes 0 GB to the totals), never `safe` |
| Outside the allowed locations (system dirs, Documents, Desktop, Downloads root, `~/.ssh`, `~/.config`, …) | `keep` |
| Project whose repo has uncommitted changes | `keep` |
| Project with a commit in the last 14 days | `keep` |
| Project without git but with files changed in the last 14 days | `keep` |
| Nothing beside it can regenerate it (no manifest or lockfile, not build output) | `ask` |
| Temp file modified in the last 24 hours | `keep` |
| Model answer missing or invalid | `ask` |
| `--apply` | typed confirmation (`DELETE <size>`), TTY required, every target listed first, git state re-read right before each delete, every path logged |

## 📊 Engineering Rigor

| Metric | Value |
|---|---|
| Tests | 64 passing (`pytest`) |
| Lint | `ruff` clean |
| Real run | nothing deleted, [evidence](evidence/dry-run-2026-10-25.md) |
| Evidence privacy | project-tree paths replaced by `~/<dir>/<project-NNN>/<artifact>`, scratch names by `$TMPDIR/<scratch-NN>`; sizes and verdicts untouched (`sweep --redact` uses the same labels on screen) |

### Honest limits (5)

1. **Hosted inference is not bit-deterministic** at temperature 0. A re-run flipped 2 of 20 borderline verdicts (the pnpm store and the cargo registry went from `safe` to `ask`). Drift can never cross a rule's cap (a KEEP never becomes a deletion), but inside a SAFE cap two runs can differ.
2. **"Safe" is a `du` figure.** pnpm-linked `node_modules` free less than they measure. `--apply` reports the measured free-space change.
3. **A full scan takes about 200 s** on a Mac with many projects: one `du` per folder (the price of honest per-item sizes), the git reads, and the model calls.
4. **Model reasons can sound factual** ("Very old browser cache") but are the model's judgement. Treat them as judgement; `decided_by` in `--json` says who decided.
5. **Some macOS-protected folders are unreadable** without Full Disk Access (14 in the run above). They show as `unreadable` and `ask`; their size is unknown and counts as 0 GB in the totals.

## 🚀 Getting Started

### Prerequisites
[uv](https://docs.astral.sh/uv/), macOS, and an [OpenRouter](https://openrouter.ai) key in `OPENROUTER_API_KEY`.

### Installation

```sh
uv tool install git+https://github.com/edycutjong/sweep   # then: sweep
uvx --from git+https://github.com/edycutjong/sweep sweep   # or run once, no install
```

### Usage

```sh
sweep                  # dry run: prints the plan, deletes nothing
sweep --json           # the plan as JSON (never deletes)
sweep --apply          # delete the SAFE items after a typed confirmation
sweep --root ~/code    # where to look for node_modules/.venv/target (repeatable)
sweep --min-mb 500     # ignore items smaller than 500 MB (default 100)
sweep --redact         # swap names under ~ for <project-NNN> / <item-NN> labels (~/Library, dot-dirs stay), to share a screenshot
```

### Weekly reminder (optional)

`sweep --install-reminder` writes a launchd job (Sundays 10:00) that runs `sweep --notify`: a dry run and one notification. It never deletes and does not load itself; it prints the `launchctl bootstrap` line to turn it on.

## 🧪 Testing & CI

```sh
uv run pytest
uv run ruff check .
```

The suite covers the hard rules, the model contract and its failure fallbacks, the CLI, and `--apply` against fixture directories only. A GitHub Actions workflow ([`ci.yml`](.github/workflows/ci.yml)) runs the same checks on `macos-latest`.

## 📁 Project Structure

```
src/sweep/
├── catalogue.py   every cache location (the one file a Linux/Windows port edits)
├── scan.py        find and size candidates, read git state
├── rules.py       hard rules and the path guard
├── model.py       the OpenRouter client and its JSON contract
├── plan.py        batch the model calls, merge verdicts
├── render.py      rich table and --json
├── apply.py       typed-confirmation delete, with a log
└── reminder.py    the optional launchd job
tests/             64 tests
evidence/          real dry run + model comparison
```

## 🗺️ Roadmap

- [x] Dry-run plan, `--json`, hard rules, model judgement
- [x] `--apply` behind a typed confirmation
- [x] Optional weekly reminder
- [ ] Linux catalogue
- [ ] Windows catalogue

## 📽️ Demo Materials

- [Real dry run, with every number](evidence/dry-run-2026-10-25.md) · [raw JSON](evidence/dry-run-2026-10-25.json)
- [Model comparison](evidence/model-spike.md)
- [Demo GIF](docs/demo.gif) · [the run behind it](evidence/demo-run-2026-10-25.md)

## 📄 License

[MIT](LICENSE)

## 🙏 Acknowledgments

Built for the [DEV Hacktoberfest Open Source AI Challenge](https://dev.to/devteam/join-the-hacktoberfest-open-source-ai-challenge-slow-and-steady-2850-in-prizes-across-21-3iee). Model by Google (Gemma), served through OpenRouter. Built with Claude Code.
