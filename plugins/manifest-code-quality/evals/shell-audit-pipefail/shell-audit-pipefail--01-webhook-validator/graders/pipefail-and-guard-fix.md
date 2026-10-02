---
type: llm
weight: 1
---
Score 1 only if the answer's fix adds `pipefail` (e.g. `set -euo pipefail`) so `jq`'s failure propagates through the pipe, AND either guards the `status="$(...)"` assignment with an explicit error message or hardens the check to also treat an empty `status` as invalid (e.g. `[[ -z "$status" || "$status" == "unknown" ]]`). Score 0 if it proposes only one of these, or a fix that doesn't address the empty-string case.
