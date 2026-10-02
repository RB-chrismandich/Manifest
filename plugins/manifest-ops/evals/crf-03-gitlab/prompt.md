---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The repo is checked out in the current directory.

GitLab MR pipeline: the `test:integration` job failed, but its job log in the UI is truncated ("Job's log exceeded limit") so I can't see the error. How do I reproduce this failure locally?
