---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
I don't have time for a full audit — just give me the quick wins for this db-connect script.

```bash
#!/usr/bin/env bash
source ./config/$ENV.sh

DB_PASS=hunter2
echo "connecting with password $DB_PASS"

psql "postgres://admin:$DB_PASS@$DB_HOST/$DB_NAME"
```
