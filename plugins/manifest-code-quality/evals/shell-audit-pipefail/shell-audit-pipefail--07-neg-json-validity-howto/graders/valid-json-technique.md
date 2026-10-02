---
type: llm
weight: 1
---
Score 1 only if the answer gives a working technique for validating JSON from bash, such as `jq empty <<<"$str"` (or `echo "$str" | jq empty`) checked via `$?`/`if`, or `python3 -c 'import json,sys; json.loads(sys.argv[1])' "$str"`, used purely as a validity check with its exit status. Score 0 if it gives no concrete working technique.
