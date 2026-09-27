---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `: "${DB_DSN:?DB_DSN must be set}"` and the `config_dir` existence check both run before the `case "$cmd"` block that handles `--help`/`-h`, so `dbtool --help` fails on that precondition before it ever reaches the help branch, AND the fix moves the `--help`/`-h` handling to the very top of the script, before the `DB_DSN` assertion and the `config_dir` check. Score 0 if it doesn't explicitly say help handling must run before those checks, or only suggests removing the checks entirely.
