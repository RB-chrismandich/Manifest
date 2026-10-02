---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
My sequential fetch job against our vendor's REST API hangs a few hundred items in. When I curl the same endpoint by hand it also hangs for 60s and then returns 503 Service Unavailable, for several different items. How do I fix this?
