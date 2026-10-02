---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
My export job's log has been silent for 30 minutes so I think it's hung. I checked twice, two minutes apart:

```
14:02  -rw-r--r-- 1 me staff 14680064 out/export.jsonl
14:04  -rw-r--r-- 1 me staff 19922944 out/export.jsonl
```
`ps` shows state R, 35% CPU. Should I kill it and restart?
