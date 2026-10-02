---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. Reports the overall status as degraded (or equivalent: not healthy/ok) because the Manifest installation receipt is absent.
2. Does NOT declare the environment healthy/OK just because harness CLIs are on PATH.
3. Reports per-harness CLI availability (which of claude, codex, gemini, cursor, antigravity, devin were found) as informational, not as the reason for failure.
4. Does not attempt to install anything or create the receipt.
