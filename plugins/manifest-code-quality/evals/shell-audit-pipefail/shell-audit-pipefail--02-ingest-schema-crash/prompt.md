---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our ingest job dies with exit 1 whenever the upstream feed writes a slightly different schema, and the only clue in the log is a raw `jq` parse error with no context about which file or field it was trying to read. Here's the script — what should I fix?

```bash
#!/usr/bin/env bash
set -euo pipefail

feed="feed.json"
record_id="$(jq -r '.payload.id' "$feed")"
region="$(jq -r '.payload.meta.region' "$feed")"

echo "processing record $record_id in $region"
```
