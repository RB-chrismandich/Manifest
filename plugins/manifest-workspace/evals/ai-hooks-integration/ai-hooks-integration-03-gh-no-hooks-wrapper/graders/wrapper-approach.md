---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Recommends a wrapper/shim for `gh` placed earlier on PATH (or equivalent executable interception) rather than per-agent hook configs as the primary mechanism, since the requirement is tool-agnostic.
2. The shown wrapper runs `/opt/audit/pr-audit.sh` only for `pr create` (or checks subcommand), aborts with a non-zero exit when the audit fails, and otherwise execs the REAL gh binary (by absolute path or by skipping itself on PATH) forwarding all arguments (`"$@"`).
3. Avoids infinite recursion (the wrapper does not call itself as `gh`).
4. Does not claim `gh` has a native pre-command hook API.
