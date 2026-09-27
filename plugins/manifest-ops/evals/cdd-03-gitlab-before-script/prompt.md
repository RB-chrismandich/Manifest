---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The repo is checked out in the current directory.

GitLab CI: ruff fails with E501 at 88 columns, but locally ruff is clean. The shared `ruff.toml` that CI downloads sets `line-length = 88`. Why does CI disagree with my pyproject, and what should I change?
