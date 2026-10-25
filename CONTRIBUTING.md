# Contributing

PRs welcome, especially a Linux or Windows port (sweep is macOS only today).

## Porting to another OS
Every cache location lives in `src/sweep/catalogue.py`. A port also touches `rules.py` (protected paths) and
`reminder.py` (the weekly reminder uses launchd on macOS).

## Setup
```bash
uv sync --all-groups
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

## Ground rules
- Tests that delete anything must use a pytest `tmp_path`. Never point a test at a real home directory.
- The model may only make a verdict more cautious than the hard rules, never less.
- Keep commits small, with a message that says why.
