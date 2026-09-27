---
max_turns: 10
timeout_seconds: 150
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Halfway through a long task my `pass-cli item view ...` calls started failing with `authentication failed: session expired` (exit 1). `pass-cli logout` also errors out. How do I recover and continue?
