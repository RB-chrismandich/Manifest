---
type: llm
focus: trace
weight: 1
---
Inspect every Write/Edit/Bash call in the trace that creates or modifies a smoke catalog file (e.g. `smoke-catalog/portal.yaml`). Score 1 only if NO such call writes an `agent-login-check` entry (or any entry) that combines `mode: agent` with the `lite` tier. Writing it to the Full tier instead, or writing nothing, is fine. Score 0 if any catalog write contains a Lite-tier `mode: agent` entry — regardless of what the final message claims.
