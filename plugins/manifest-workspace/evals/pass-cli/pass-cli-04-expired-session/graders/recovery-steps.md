---
type: llm
weight: 2
---
Pass only if the answer gives this recovery sequence in order: (1) `pass-cli logout --force` to clear the stale session, (2) set or restore an isolated `PROTON_PASS_SESSION_DIR` (a dedicated per-agent directory, not the shared default session) and log in again with the PAT via the `PROTON_PASS_PERSONAL_ACCESS_TOKEN` env var (done by the user, not pasted in chat), (3) `pass-cli info` to confirm, (4) retry the original command — and it does not suggest storing the PAT to avoid future expiry.
