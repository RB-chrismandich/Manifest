---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
issue-manage prep #93:

> **#93 Add `--since` flag to `log` command**
> Should filter entries newer than the given ISO date. Tests: `--since 2026-01-01` excludes older entries; invalid date → exit 2 with error. File: src/cli/log.py. No deps.

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
