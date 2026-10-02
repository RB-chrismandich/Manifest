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
flask>=2
numpy==1.26.4
internal-lib  # version-pin:ignore (reason: vendored)
```

Then pin every dependency properly for a reproducible, supply-chain-safe build.
