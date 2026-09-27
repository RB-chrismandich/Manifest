---
max_turns: 10
timeout_seconds: 240
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our release step sometimes just stops with a `jq` parse error buried in the CI log and no explanation from the script itself — everything downstream gets skipped. Here's the relevant chunk, what's the fix?

```bash
#!/usr/bin/env bash
set -euo pipefail

plan="plan.json"
services="$(jq -r '.services[]' "$plan")"
echo "services to deploy: $services"

for svc in $services; do
  echo "queuing $svc"
done
```
