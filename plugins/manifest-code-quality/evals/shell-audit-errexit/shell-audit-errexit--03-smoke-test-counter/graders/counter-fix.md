---
type: llm
weight: 1
---
Score 1 only if the proposed fix replaces BOTH `((passed++))` and `((failed++))` with forms that always succeed under `set -e` — e.g. `passed=$((passed + 1))`, `((++passed))`, `((passed += 1))`, `: $((passed++))`, or `((passed++)) || true` (and the same for `failed`). Score 0 if either counter is left as a bare post-increment that can evaluate to 0 and abort.
