---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
I opened a PR that adds a stricter `if:` gate to our `issue_comment`-triggered bot workflow, then commented on that PR to test it — but the old, looser gate still ran. Is GitHub broken? How should I test the new gate?
