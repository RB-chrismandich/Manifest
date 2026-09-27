---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Audit this webhook payload validator — can a malformed payload ever slip through and get treated as valid?

```bash
#!/usr/bin/env bash
set -eu

payload="$1"

status="$(echo "$payload" | jq -r '.status' | sed 's/null/unknown/')"

if [[ "$status" == "unknown" ]]; then
  echo "rejecting payload with no status" >&2
  exit 1
fi

echo "processing payload with status=$status"
```
