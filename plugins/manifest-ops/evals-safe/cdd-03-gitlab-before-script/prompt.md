---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
GitLab reports ruff `E501` at 88 columns, although local checks are clean and `pyproject.toml` sets a 120-character limit. The CI setup imports shared lint configuration before running ruff. Trace which setting wins and recommend a deliberate fix; distinguish configuration drift from a need to reformat source files.
