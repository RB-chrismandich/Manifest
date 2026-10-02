---
max_turns: 10
timeout_seconds: 240
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This cron job dies after the first email with no error message at all — why, and how do I fix it?

```bash
#!/usr/bin/env bash
set -euo pipefail

count=0
for f in inbox/*.eml; do
  ./parse_email.sh "$f"
  ((count++))
done
echo "processed $count emails"
```
