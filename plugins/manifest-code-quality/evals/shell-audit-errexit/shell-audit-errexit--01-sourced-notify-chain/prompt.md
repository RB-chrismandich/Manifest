---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We have a deploy script that occasionally stops before printing the final "rollout complete" line — exit code 1, nothing in the logs, and the services actually did get restarted. Can you audit `deploy.sh` and the two helper libs it sources for anything that could abort the whole run under strict mode?

deploy.sh:
```bash
#!/usr/bin/env bash
set -euo pipefail

source lib/rollback.sh
source lib/notify.sh

rollout() {
  for svc in api worker scheduler; do
    echo "rolling out $svc"
    systemctl restart "$svc"
  done
}

rollout
notify_done "rollout complete for api worker scheduler"
echo "rollout complete"
```

lib/rollback.sh:
```bash
register_rollback() {
  ROLLBACK_STACK+=("$1")
}
```

lib/notify.sh:
```bash
notify_done() {
  local msg="$1"
  echo "notifying: $msg"
  [[ -n "${SLACK_WEBHOOK:-}" ]] && post_to_slack "$msg"
}

post_to_slack() {
  echo "POST $SLACK_WEBHOOK -> $1"
}
```
