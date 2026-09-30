---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
What's the cleanest way to support both `--flag=value` and `--flag value` syntax when parsing arguments in a bash script?
