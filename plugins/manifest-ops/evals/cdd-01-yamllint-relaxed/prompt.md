---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The repo is checked out in the current directory.

yamllint passes locally but fails in GitHub Actions. CI output: 14 findings like `deploy/values.yaml:42:81 [warning] line too long (97 > 80 characters) (line-length)` and the step exits 2. Locally `yamllint .` shows nothing. What's going on and how should I fix it?
