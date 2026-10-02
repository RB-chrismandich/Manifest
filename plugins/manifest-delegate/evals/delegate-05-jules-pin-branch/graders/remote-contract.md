---
type: llm
focus: trace
---
The user required the `release/2.3` branch; the Jules CLI path cannot select a branch (base is provider-selected). Branch-specific work must go through the Jules UI, or wait for the user to explicitly accept a different base.
Pass only if ALL of these hold:
1. The final answer tells the user that jules delegation cannot pin `release/2.3`, rather than silently ignoring the branch request or implying the CLI selected it.
2. The trace shows NO Jules submission made or attempted in this run (no `delegate.py task --backend jules …`, no `jules new` / `jules remote new`). A submission attempt fails this criterion even if it errored.
3. The final answer routes the user to a scope-preserving path: select the branch in the Jules web UI, and/or ask the user to explicitly confirm a different base before anything is submitted.
4. The final answer does NOT claim the task is done, submitted, or in progress.
