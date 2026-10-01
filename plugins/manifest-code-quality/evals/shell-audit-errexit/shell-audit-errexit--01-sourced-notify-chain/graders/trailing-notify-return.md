---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `notify_done`'s last statement is `[[ -n "${SLACK_WEBHOOK:-}" ]] && post_to_slack "$msg"`, so when `SLACK_WEBHOOK` is unset the `&&` list returns non-zero, that becomes `notify_done`'s return status, and the bare call `notify_done "..."` in deploy.sh (not wrapped in an `if`/`&&`/`||`) aborts the script under `set -e` before the final `echo "rollout complete"` line — explaining that the rollout itself already happened even though the script died. Score 0 if this mechanism is missing or misattributed (e.g., blamed on `systemctl` or the `source` lines).
