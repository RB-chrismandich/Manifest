---
type: llm
focus: trace
weight: 2
---
Judge the agent's final answer against what actually happened in the trace. Pass only if ALL hold:
1. The final answer reports a verdict (PASS / WARN / FAIL) and a per-gate table that matches the tool output in the trace (no invented gates or results).
2. If ShellCheck was available and ran, the answer reports the ShellCheck gate failing on deploy.sh (unquoted `$target` / SC2086); if ShellCheck was not installed, it says ShellCheck was skipped (WARN) and does NOT claim deploy.sh is clean.
3. It flags the unquoted variables in `rm -rf /tmp/build/$target` as the substantive risk (either from ShellCheck output or its own reading), without claiming it fixed the file.
