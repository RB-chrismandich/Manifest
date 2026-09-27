---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
`notify_all.sh` is supposed to email every address in `recipients.txt` but our logs show it only ever sends to the first person, then the job just ends with exit 0 — no error at all. Can you figure out why?

```bash
#!/usr/bin/env bash
set -euo pipefail

cat recipients.txt | while IFS= read -r addr; do
  echo "emailing $addr"
  mail -s "Nightly report: $(date +%F)" "$addr"
done
echo "all reports sent"
```
