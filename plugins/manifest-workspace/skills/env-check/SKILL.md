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

When independent readiness dimensions require review, assign bounded read-only
`scout` units through the deployed host's shared native dispatch contract. The
parent directly aggregates attributed evidence.
