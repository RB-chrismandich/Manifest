---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
ruff fails in CI with `app/api.py:3:8: F401 [*] 'os' imported but unused`. I ran `ruff check .` locally and get the exact same error. How do I fix it?
