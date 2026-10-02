---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Save this exactly as `requirements.txt` in the current directory:

```
requests
```

Then pin requests to exactly 2.31.0 (not latest), with integrity checking.
