---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Our bot workflow is gated on an allowlist in `.github/bot-allowlist.txt`. How do I make sure a collaborator can't just open a PR that adds themselves to the allowlist or edits the workflow gate, while I (sole maintainer) can still merge my own PRs?
