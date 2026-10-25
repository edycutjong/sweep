# sweep

A lazy disk-cleanup agent for macOS. Work in progress — full README coming.

macOS only for now — adding Linux or Windows is a single pull request, PRs welcome.

## Install

Needs [uv](https://docs.astral.sh/uv/) and an [OpenRouter](https://openrouter.ai) key (`OPENROUTER_API_KEY`).

```sh
uv tool install git+https://github.com/edycutjong/sweep   # then: sweep
uvx --from git+https://github.com/edycutjong/sweep sweep   # or run once, no install
```

`sweep` is a dry run: it prints a plan and deletes nothing. `sweep --json` prints the plan as JSON.

## Weekly reminder (optional)

`sweep --install-reminder` writes a launchd job (Sundays 10:00) that runs `sweep --notify`: a dry run and one
notification. It never deletes and does not load itself; it prints the `launchctl bootstrap` line to turn it on.

## Evidence

A real dry run on the author's Mac, with every number: [`evidence/dry-run-2026-10-25.md`](evidence/dry-run-2026-10-25.md).
Model comparison: [`evidence/model-spike.md`](evidence/model-spike.md).
