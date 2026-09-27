---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The repo is checked out in the current directory.

This is a GitLab Ultimate, group-owned project. Our pipeline has a `policy-lint` job that fails on eslint `max-len: 80`, but nothing in this repo defines it, and `glab ci config compile` output contains no `policy-lint` job and no eslint invocation. Where is `policy-lint` coming from and how do we get the thresholds aligned?
