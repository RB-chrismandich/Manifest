---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This nightly job that grabs a 200-line sample of live events keeps failing — `sample.txt` gets written with all 200 lines, but the script itself exits non-zero right after and the rest of the nightly job never runs. Can you explain what's happening and fix it?

```bash
#!/usr/bin/env bash
set -euo pipefail

generate_events() {
  local i=0
  while true; do
    i=$((i + 1))
    echo "event $i: user_login uid=$i"
  done
}

generate_events | head -n 200 > sample.txt
echo "wrote 200-line sample to sample.txt"
```
