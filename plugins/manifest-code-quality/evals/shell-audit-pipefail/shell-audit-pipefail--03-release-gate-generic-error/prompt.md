---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
This release-gate script already has error handling, but on-call says the failure emails are useless — just "Error: something went wrong" with no idea what actually broke. Can you review it and tell us what to fix?

```bash
#!/usr/bin/env bash
set -euo pipefail

fetch_release_info() {
  cat "$1"
}

response="$(fetch_release_info release.json)"
version="$(echo "$response" | jq -r '.version')" || { echo "Error: something went wrong" >&2; exit 1; }
channel="$(echo "$response" | jq -r '.channel')" || { echo "Error: something went wrong" >&2; exit 1; }

echo "gating release $version on channel $channel"
```
