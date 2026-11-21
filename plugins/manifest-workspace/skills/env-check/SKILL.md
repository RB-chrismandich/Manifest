---
name: env-check
description: Inspect the Manifest installation receipt and native harness inventories for availability and capability degradation using only bundle-local code and XDG state.
---

# Environment Check

Run `scripts/env_check.py --json`. It reads the installation receipt at
`$XDG_STATE_HOME/manifest/installation.json` and reports receipt claims separately
from native observations. Without a saved native report, status is `unverified`;
it is never healthy based only on executable presence. To supply native evidence,
run the read-only `manifest reconcile --json` path and pass its saved output with
`--native-evidence PATH` (or pipe it to `--native-evidence -`). That command may
resolve a release source; do not run it when network-free operation is required.
Authentication and operation-level capability are always reported as not tested.
The script itself performs no network calls, installation, authentication prompts,
or writes.

Missing or malformed receipts, empty selected targets, incomplete native
observations, and receipt/native drift are non-success. Unselected harnesses
remain informational. Do not inspect another harness's home or use one tool's
settings to verify another tool.
