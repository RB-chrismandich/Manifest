---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our release job sometimes just stops with exit 1 and no output at all. The upstream step writes `plan.json`. Can you check this script for the silent-abort risk?

```bash
#!/usr/bin/env bash
set -euo pipefail

plan_file="${PLAN_FILE:-plan.json}"
targets="$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["targets"]))' "$plan_file")"
dropped="$(jq -r '.dropped | length' "$plan_file")"

if [[ -z "$targets" ]]; then
  echo "nothing to release"
  exit 0
fi
if (( dropped > 0 )); then
  echo "warning: $dropped candidates were rejected" >&2
fi
for t in $targets; do ./release_one.sh "$t"; done
```
