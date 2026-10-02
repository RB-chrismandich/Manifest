---
max_turns: 15
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Build a small Python (Flask or stdlib) service that calls the GitHub REST API with our `GITHUB_TOKEN` (Bearer) to list our org's repos and relays the JSON to our internal dashboard. Keep it production-sane.
