---
type: llm
weight: 1
---
Score 1 only if the answer ALSO flags `dropped="$(jq -r '.dropped | length' "$plan_file")"` as an unguarded command substitution that aborts under `set -e` when plan.json is missing or malformed (jq exits non-zero, leaving only raw jq stderr), AND recommends a guard with a step-naming error message and/or a jq default such as `(.dropped // []) | length`. Score 0 if this second substitution is not addressed.
