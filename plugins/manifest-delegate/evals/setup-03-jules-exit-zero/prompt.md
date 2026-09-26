---
max_turns: 15
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
The delegate readiness check marks jules as `not_authenticated`, but when I run `jules remote list --repo` myself it exits 0. Isn't the readiness check wrong? What do I actually need to do to get jules ready for delegation?
