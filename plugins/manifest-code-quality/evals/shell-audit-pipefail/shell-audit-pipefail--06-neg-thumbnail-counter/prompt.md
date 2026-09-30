---
max_turns: 10
timeout_seconds: 240
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This thumbnail batch job dies right after processing the very first image — no error text, no partial-progress log, nothing. Any idea why?

```bash
#!/usr/bin/env bash
set -euo pipefail

processed=0
for img in inbox/*.png; do
  convert "$img" -resize 200x200 "thumbs/$(basename "$img")"
  ((processed++))
done
echo "processed $processed images"
```
