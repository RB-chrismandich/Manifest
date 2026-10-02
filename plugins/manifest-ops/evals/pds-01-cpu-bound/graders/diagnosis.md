---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It classifies this as CPU-bound work (state R, ~100% CPU), not an I/O/network hang, and pushes back on the API/retries theory.
2. It recommends measuring where time goes: a live stack (`py-spy dump --pid 51234`) or timing each phase on real data.
3. It points to likely fix classes: bounding an unexpectedly large input (e.g. window-filtering full history) and/or memoizing an expensive call in an inner loop.
4. It does NOT recommend adding retries or network timeouts as the fix.
