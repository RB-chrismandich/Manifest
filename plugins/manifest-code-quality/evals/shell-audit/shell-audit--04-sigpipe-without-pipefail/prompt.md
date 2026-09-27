---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Pre-commit review: please do a shell safety audit of this cleanup script and rank anything that can make it exit early.

```bash
#!/usr/bin/env bash
set -eu

log_dir="${1:?usage: prune.sh <log-dir>}"

newest="$(ls -t "$log_dir"/*.log | head -1)"
echo "keeping newest: $newest"

ls -t "$log_dir"/*.log | head -n 20 | while IFS= read -r f; do
  gzip -f "$f"
done

owner="$(stat -c %U "$newest")"
echo "logs owned by $owner"
```
