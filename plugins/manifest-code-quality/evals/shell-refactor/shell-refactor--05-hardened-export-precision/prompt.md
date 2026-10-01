---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Can you review this export script before I merge it? Flag anything that actually needs fixing.

```bash
#!/usr/bin/env bash
set -euo pipefail

api_token="${API_TOKEN:?API_TOKEN must be set}"
tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

curl -sf -H "Authorization: Bearer ${api_token}" "https://api.example.com/export" -o "$tmpfile"
jq '.items[] | select(.active == true)' "$tmpfile"
```
