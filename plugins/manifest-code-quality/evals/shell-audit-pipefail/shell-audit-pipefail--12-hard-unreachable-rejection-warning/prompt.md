---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This candidate-filter job is supposed to warn us when every candidate in a batch gets rejected, but on a bad batch we just saw it exit clean with zero warning output and nothing processed. Can you figure out why?

```bash
#!/usr/bin/env bash
set -euo pipefail

candidates=("$@")
valid=()
rejected=0

for c in "${candidates[@]}"; do
  if [[ "$c" =~ ^a[0-9]+$ ]]; then
    valid+=("$c")
  else
    rejected=$((rejected + 1))
  fi
done

if [[ ${#valid[@]} -eq 0 ]]; then
  exit 0
fi

if (( rejected > 0 )); then
  echo "warning: $rejected candidates rejected as malformed" >&2
fi

printf 'processing %s\n' "${valid[@]}"
```
