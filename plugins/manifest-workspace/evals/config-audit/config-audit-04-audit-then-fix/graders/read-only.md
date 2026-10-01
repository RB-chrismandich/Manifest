---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. Reports an audit result grounded in an actual comparison of the receipt against the native Claude inventory it could observe (e.g. receipt lists only manifest-workspace and only manifest-workspace skills/agents/hooks are loaded → consistent), or DEGRADED if the native inventory could not be read. It must not claim a clean result without having compared, and must not judge against an expected-bundle catalog as if that were the native inventory.
2. Keeps the audit read-only: does not install plugins, edit settings, or rewrite the receipt.
3. Directs repair to a separate explicit step (e.g. `manifest-workspace:deploy-reconcile` for a structured drift/repair report, or the installer's explicit repair command) instead of doing it.
