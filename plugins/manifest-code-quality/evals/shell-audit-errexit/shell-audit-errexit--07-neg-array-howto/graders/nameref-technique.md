---
type: llm
weight: 1
---
Score 1 only if the answer explains passing the array's NAME (not the array itself) into the function and using a nameref inside it — e.g. `local -n ref="$1"` or `declare -n ref="$1"` — to operate on the caller's associative array by reference. Score 0 if it does not mention nameref/`-n` (e.g. only suggests globals, or claims arrays can be passed by value, or suggests serializing to a string).
