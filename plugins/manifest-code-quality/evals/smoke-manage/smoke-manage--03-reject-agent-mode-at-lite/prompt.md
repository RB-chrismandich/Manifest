---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(find:*)"]
runs: 3
---
Add a smoke test for the `portal` app called `agent-login-check` that uses the AI browser agent (`mode: agent`) to log in as the demo user and confirm the dashboard loads. Since it's quick, put it in the `Lite` tier so it runs on every PR.
