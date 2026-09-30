---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Here's a query helper from our ops toolbox — does this look production ready?

```bash
#!/usr/bin/env bash
set -e

run_query() {
  local filter="$1"
  eval "grep $filter /var/log/app.log" > /tmp/query-result.txt
  cat /tmp/query-result.txt
}

run_query "$1"
```
