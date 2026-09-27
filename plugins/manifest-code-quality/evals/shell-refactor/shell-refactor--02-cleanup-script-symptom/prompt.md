---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Security flagged this log-cleanup script in our last audit — can you give me a fix roadmap with priorities?

```bash
#!/usr/bin/env bash
API_TOKEN="hardcoded-example-token"  # gitleaks:allow
LOG_DIR=/var/log/app

cleanup() {
  local pattern=$1
  find "$LOG_DIR" -name $pattern -exec rm -f {} \;
}

cleanup "*.log"

curl -s -H "Authorization: Bearer $API_TOKEN" https://api.example.com/purge
```
