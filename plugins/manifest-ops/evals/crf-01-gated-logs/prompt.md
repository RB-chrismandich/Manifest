---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The repo is checked out in the current directory.

GitHub Actions run 9912345678 on my PR: the `lint-and-generate` job has a red X, but `gh run view 9912345678 --log-failed` just says "run 9912345678 is still in progress; logs will be available when it is complete". The e2e job will keep running for another ~40 minutes. How do I find out what failed and reproduce it right now?
