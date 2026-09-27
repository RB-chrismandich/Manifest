---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The repo is checked out in the current directory.

Markdown lint is red on every PR in CI but clean on my machine. CI errors are all `MD013/line-length` and `MD033/no-inline-html`. Locally I run `npx markdownlint-cli2 "**/*.md"`. Why the difference and what's the right fix?
