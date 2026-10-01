---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The repo is checked out in the current directory.

The jobs API shows for job `checks`: steps 1-3 completed success, step 4 `Verify generated files are up to date` completed failure, step 5 `Unit tests` skipped. Tests pass locally. What's the failure and how do I fix it?
