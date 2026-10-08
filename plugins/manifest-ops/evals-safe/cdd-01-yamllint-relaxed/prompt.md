---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
This repository is open in the current directory. GitHub Actions reports 14 `line-length` warnings from yamllint and exits with status 2, while running `yamllint .` locally reports none. Explain the mismatch from the checked-in workflow and config, then recommend the smallest policy-consistent correction. Do not treat rewriting all 14 YAML lines as the default fix.
