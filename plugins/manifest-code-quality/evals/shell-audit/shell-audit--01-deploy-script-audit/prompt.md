---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Audit this deploy script for ways it can abort silently under `set -euo pipefail`. Report findings by severity with a fix for each. Don't rewrite the whole script.

```bash
#!/usr/bin/env bash
set -euo pipefail

remove_stale_agent() {
  local plist="$HOME/Library/LaunchAgents/com.acme.sync.plist"
  echo "checking for stale agent"
  [[ -f "$plist" ]] && rm -f "$plist"
}

deployed=0
version="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])' < release.json)"
echo "deploying $version"

cat hosts.txt | while IFS= read -r host; do
  ssh "$host" "sudo systemctl restart acme"
  ((deployed++))
  echo "restarted $host"
done

remove_stale_agent
echo "Deployed $version to all hosts"
```
