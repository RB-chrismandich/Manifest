---
name: env-check
description: Inspect the Manifest installation receipt and native harness inventories for availability and capability degradation using only bundle-local code and XDG state.
---

# Environment Check

Run `scripts/env_check.py --json`. It reads the installation receipt at
`$XDG_STATE_HOME/manifest/installation.json` and checks whether native harness
executables are present on `PATH`. It performs no network calls, installation,
authentication prompts, or writes.

An absent or unreadable receipt yields `status: degraded` with a warning.
Unavailable optional harnesses remain informational. Do not inspect another
harness's home or use one tool's settings to verify another tool.

For a cross-provider orchestration readiness check, invoke
`manifest-workspace:parallel-agent` and consume its structured result when supported.
