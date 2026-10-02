---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `((passed++))` (and equivalently `((failed++))`) with the counter starting at 0 evaluates to the OLD value 0 on the first increment, so the arithmetic command returns exit status 1, and under `set -e` this aborts the script immediately after the first test passes (or fails) — meaning the loop never finishes and the `summary:` line never prints. Score 0 if it misses this mechanism or treats the bug as only a cosmetic off-by-one in the printed counts.
