---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
In this repository, CI reports Markdown `MD013` and `MD033` violations on every pull request, but my local `npx markdownlint-cli2 "**/*.md"` run is clean. Inspect the committed configs and workflow, explain why the results differ, and suggest a policy-consistent fix rather than mass-editing the docs by default.
