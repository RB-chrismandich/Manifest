---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Edit, Read, Grep, Glob, "Bash(mkdir:*)", "Bash(ln:*)"]
runs: 3
---
I already have a `pyproject.toml` for this project — save the file below exactly as given, then scaffold whatever quality-gate tooling is still missing for `existing-thing` (lint, tests, pre-commit). Don't touch files that are already there.

`pyproject.toml`:
```toml
[project]
name = "existing-thing"
version = "0.4.0"
description = "hand-rolled config, do not clobber"

[tool.ruff]
line-length = 100
```
