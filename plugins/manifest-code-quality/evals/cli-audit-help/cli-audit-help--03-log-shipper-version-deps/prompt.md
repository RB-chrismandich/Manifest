---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Adding a `--version` flag to our log-shipper script. Here's the current top of the file — does this look right before I open the PR?

```bash
#!/usr/bin/env bash
set -euo pipefail

command -v jq >/dev/null 2>&1 || { echo "log-shipper: jq is required" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "log-shipper: curl is required" >&2; exit 1; }

VERSION="2.3.0"
if [[ "${1:-}" == "--version" ]]; then
  echo "log-shipper $VERSION"
  exit 0
fi

log_file="${1:?usage: log-shipper <log-file>}"
echo "shipping $log_file"
```
