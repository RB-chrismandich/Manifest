---
type: llm
focus: trace
weight: 2
---
Judge the final answer against what the runner actually printed in the trace (full mode). Pass only if ALL hold:
1. It reports the verdict and exit code the runner actually produced.
2. It explains the exit codes correctly: 0 = PASS, 1 = WARN (optional tools missing), 2 = FAIL (a gate ran and failed).
3. For every gate the trace shows was skipped because its tool isn't installed, the answer reports it as WARN (missing tool), not FAIL — and if the trace shows no missing tools, it says so rather than inventing any.
4. If the runner reported FAIL only because of gates for scripts/files this repo doesn't have (e.g. Manifest-only `tests/lint/check_*.sh`), the answer identifies that as a runner/tooling problem unrelated to this repo, not a regression in it.
