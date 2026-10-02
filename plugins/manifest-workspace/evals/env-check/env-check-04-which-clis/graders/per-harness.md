---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Reports availability for each of the six harness binaries Manifest checks: claude (`claude`), codex (`codex`), gemini (`gemini`), cursor (`cursor-agent`), antigravity (`agy`), devin (`devin`) — each marked available or missing, consistent with what the trace shows.
2. Notes the Manifest receipt is absent / status degraded (it is not installed yet), without treating that as an error in the CLI check.
3. Does not install, authenticate, or make network calls.
