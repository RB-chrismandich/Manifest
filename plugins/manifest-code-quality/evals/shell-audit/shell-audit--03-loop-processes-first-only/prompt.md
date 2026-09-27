---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Can you audit `summarize.sh`? It's supposed to summarize every file listed in `queue.txt` but it only ever does the first one and then exits 0.

```bash
#!/usr/bin/env bash
set -euo pipefail

queue="queue.txt"
[[ -s "$queue" ]] || { echo "empty queue" >&2; exit 1; }

cat "$queue" | while IFS= read -r path; do
  echo "== $path"
  claude -p "Summarize this file in 3 bullets: $(cat "$path")" > "summaries/$(basename "$path").md"
done
```
