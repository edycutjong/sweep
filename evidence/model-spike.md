# Model spike — which open-weight model can judge disk items reliably?

Measured 2026-10-25 on the builder's Mac (macOS, Apple silicon) via OpenRouter. This decided the pinned model.

**Method.** 20 real items from a read-only scan of the Mac (13 cache/system locations from the catalogue + 7
regenerable project folders). Metadata only: name, kind, size in GB, age in days, and for project folders the
parent repo's last-commit age and dirty flag — never file contents. Each model got the same system prompt
(`src/sweep/model.py`), `temperature: 0`, `response_format: json_object`, in 2 batches of 10, 3 runs each
(6 calls per model). An entry counts as valid only if the reply is bare JSON (no code fence), the entry has
exactly the keys `id, verdict, reason`, the id is one we sent, the verdict is `safe|ask|keep`, and the reason
is 1–200 characters. "Unsafe SAFE" = the model said `safe` for Downloads, simulator data, or a project folder
whose repo is dirty or committed to in the last 14 days (the hard rules would block these anyway).

| Model | Valid entries per run (of 20) | Calls OK | Latency p50 per 10-item call | Unsafe SAFE verdicts |
|---|---|---|---|---|
| `google/gemma-4-31b-it` **(pinned)** | 20 / 20 / 20 | 6/6 | 7.35 s | 0 |
| `google/gemma-3-27b-it` | 20 / 20 / 20 | 6/6 | 7.67 s | 0 |
| `openai/gpt-oss-120b` | 20 / 20 / 20 | 6/6 | 8.01 s | 0 |
| `meta-llama/llama-3.3-70b-instruct` | 20 / 20 / 20 | 6/6 | 10.19 s | 0 |
| `qwen/qwen3-235b-a22b-2507` | 20 / 20 / 20 | 6/6 | 14.76 s | 0 |

**Why `google/gemma-4-31b-it`.** Every model met the JSON bar (≥18/20), so the choice came down to the
reasons, which are what the user reads in the plan. Gemma 4 gave specific, regenerability-based reasons
("PNPM store is regenerable.", "Rust target directory is a regenerable build artifact.") and was the only one
to mark the Trash `ask` ("may want to recover"). Gemma 3 27B passed too but gave size-only reasons ("It's a
large npm cache.") and marked the Trash `safe`. Gemma 4 also had the lowest p50 latency of the five.

**Caveat — not bit-deterministic.** Weights are pinned and `temperature` is 0, but hosted inference can still
vary: a re-run of the shipped `sweep.model.judge()` the same evening returned 20/20 valid again with 2 of 20
verdicts changed (`~/Library/pnpm` and `~/.cargo/registry` went `safe` → `ask`, the cautious direction).
sweep's hard rules run before the model and a model verdict can only make an item more cautious, so this
variance can never turn a KEEP into a deletion.

## Run-1 verdicts from the pinned model

| id | item | kind | size GB | age d | repo last commit d | dirty | verdict | reason |
|---|---|---|---|---|---|---|---|---|
| i1 | `~/Library/Caches/Google` | browser-cache | 0.11 | 59.2 |  |  | safe | Standard browser cache that can be regenerated. |
| i2 | `~/Library/Caches/com.apple.Safari` | browser-cache | 0.0 | 22.1 |  |  | safe | Standard browser cache that can be regenerated. |
| i3 | `~/Library/Caches/pip` | package-cache | 0.18 | 1.6 |  |  | safe | Python package cache can be redownloaded. |
| i4 | `~/Library/Caches/Homebrew` | package-cache | 0.41 | 5.0 |  |  | safe | Homebrew cache can be redownloaded. |
| i5 | `~/.npm` | package-cache | 3.63 | 5.0 |  |  | safe | NPM cache is regenerable. |
| i6 | `~/Library/pnpm` | package-cache | 13.94 | 5.0 |  |  | safe | PNPM store is regenerable. |
| i7 | `~/.gradle/caches` | build-cache | 9.82 | 39.3 |  |  | safe | Gradle build caches are regenerable. |
| i8 | `~/.cargo/registry` | package-cache | 0.89 | 267.4 |  |  | safe | Cargo registry can be redownloaded. |
| i9 | `~/Library/Developer/Xcode/DerivedData` | build-cache | 0.0 | 43.9 |  |  | safe | Xcode DerivedData is temporary build output. |
| i10 | `~/Library/Developer/CoreSimulator` | simulator-data | 2.34 | 213.5 |  |  | ask | Simulator data may contain user-installed apps or test state. |
| i11 | `~/.Trash` | trash | 0.0 | 0.4 |  |  | ask | Trash contains files the user explicitly deleted but may want to recover. |
| i12 | `~/Downloads` | downloads | 0.0 | 0.3 |  |  | ask | Downloads folder often contains important user files. |
| i13 | `~/Library/Caches/ms-playwright` | browser-binaries | 3.17 | 0.3 |  |  | safe | Playwright browser binaries can be re-downloaded automatically. |
| i14 | `shipcheck/node_modules` | regenerable-project-folder | 0.21 | 48.9 | no repo |  | safe | Old node_modules folder that can be rebuilt via npm/yarn. |
| i15 | `build/node_modules` | regenerable-project-folder | 0.27 | 0.1 | 0.0 | True | keep | Active project with uncommitted changes and very recent activity. |
| i16 | `program/target` | regenerable-project-folder | 1.3 | 21.2 | 15.5 | False | safe | Rust target directory is a regenerable build artifact. |
| i17 | `build/node_modules` | regenerable-project-folder | 0.15 | 20.7 | 20.3 | False | safe | Old node_modules folder that can be rebuilt. |
| i18 | `assets/node_modules` | regenerable-project-folder | 0.02 | 36.7 | no repo |  | safe | Old node_modules folder that can be rebuilt. |
| i19 | `assets/node_modules` | regenerable-project-folder | 0.02 | 40.1 | no repo |  | safe | Old node_modules folder that can be rebuilt. |
| i20 | `casino-sdk/node_modules` | regenerable-project-folder | 0.28 | 51.3 | no repo |  | safe | Old node_modules folder that can be rebuilt. |

Sizes are `du -sk` on the day. `~/.Trash` reads as 0 because macOS blocks it without Full Disk Access.
