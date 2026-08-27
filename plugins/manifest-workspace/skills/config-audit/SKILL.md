---
name: config-audit
description: Audit installed Manifest plugin receipts and each harness's native inventory for configuration drift without treating one harness as shared storage.
---

# Configuration Audit

Read `$XDG_STATE_HOME/manifest/installation.json` and compare the receipt with
each selected harness's own native plugin, hook, agent, rule, and guidance
inventory. Do not inspect another harness's settings as a proxy.

Report each capability as `native`, `generated`, `imported`, `degraded`, or
`unsupported`, matching the bundle contract. Missing or malformed receipt data
is `DEGRADED`, never clean. Keep the audit read-only.

Use `manifest-workspace:deploy-reconcile` when the user needs a structured drift report
that names repair requirements.
