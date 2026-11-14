---
name: deploy-reconcile
description: Compare Manifest installation receipts, portable bundle contracts, and harness-native inventories; report structured drift and whether an explicit repair is required.
---

# Plugin Reconcile

Run `scripts/plugin_reconcile.py --json`. The command is analysis-only and
reads `$XDG_STATE_HOME/manifest/installation.json`; it never calls bootstrap or
the ephemeral coordinator and never mutates an installed harness.

The result includes `status`, `drift[]`, `receipt`, `repair_required`, and
`unverified[]`. Each drift item names the harness and missing, extra, stale,
or disabled capability. Receipt-only agreement is never convergence.

Before claiming convergence, obtain a read-only native report with
`manifest-agent reconcile --json` and pass it as `--native-inspection PATH`
(or pipe it with `--native-inspection -`). This is the coordinator's typed
`native_inspection` output; the script does not invoke the coordinator or
implement a second package manager. Missing, malformed, partial, or unreadable
native evidence yields `degraded`/unverified. If repair is required, point the
user to the installation documentation's explicit `uvx` repair command. Do not
infer authorization to repair from an audit request.

## Sub-agent dispatch

Follow the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
The parent compares independently collected harness inventories directly.
