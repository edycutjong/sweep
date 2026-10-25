# Security policy

sweep deletes files, so safety bugs matter. Report anything that could make it delete something it should not
(a bypassed hard rule, a path-guard escape, a verdict merge that is less cautious than the rules, `--apply` acting
without the typed confirmation).

Please use GitHub's private vulnerability reporting (Security tab → Report a vulnerability) rather than a public
issue. Expect a first reply within a few days.

Never put your OpenRouter key in an issue, log or pull request. sweep reads it from the environment or
`~/.config/openrouter/credentials.json` and never writes it anywhere.
