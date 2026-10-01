---
type: llm
weight: 1
---
Score 1 only if the answer flags `((deployed++))` with `deployed=0` as returning exit status 1 (the post-increment evaluates to the old value 0) which aborts under `set -e`, AND proposes an always-succeeding form such as `deployed=$((deployed + 1))` or `((deployed++)) || true`. Score 0 otherwise. (Noting that the counter is lost in the pipeline subshell is a bonus, not required.)
