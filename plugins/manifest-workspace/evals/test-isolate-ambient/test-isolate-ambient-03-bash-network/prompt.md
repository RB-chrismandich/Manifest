---
max_turns: 25
timeout_seconds: 480
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Create `fetch_status.sh` in the current directory with exactly:

```bash
#!/usr/bin/env bash
set -euo pipefail
token=$(cat "$HOME/.statusrc")
curl -fsS -H "Authorization: Bearer $token" https://status.example.com/api/v1/health
```

Write a plain-bash test script `test_fetch_status.sh` (no bats needed) for it covering the happy path and the missing-token case, and run it. It must not hit the network or read my real home.
