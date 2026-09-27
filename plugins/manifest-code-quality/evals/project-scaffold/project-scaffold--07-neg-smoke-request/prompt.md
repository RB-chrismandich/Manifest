---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
We just shipped the login flow for the `billing` app. Add a Lite-tier smoke test that hits `POST /api/login` and expects a 200.

Don't create any files yet — just tell me exactly what you'd add (file names and their contents).
