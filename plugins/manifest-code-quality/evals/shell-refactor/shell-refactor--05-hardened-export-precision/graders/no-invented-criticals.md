---
type: llm
weight: 1
---
This script is already hardened (`set -euo pipefail`, guarded `${API_TOKEN:?...}`, `mktemp` with an `EXIT` trap for cleanup, quoted variables throughout, no `eval`). Score 1 only if the answer does NOT report a Critical/High finding for: the temp-file handling, the secret/token handling, unquoted expansions, or `eval` usage. Score 0 if it invents a Critical/High finding on any of those already-handled patterns.
