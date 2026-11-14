---
name: deploy-reconcile
description: Compare Manifest installation receipts, portable bundle contracts, and harness-native inventories; report structured drift and whether an explicit repair is required.
---

# Plugin Reconcile

Run `scripts/plugin_reconcile.py --json`. The command compares a strictly
validated installation receipt with the harness-native evidence supplied via
`--native-evidence PATH` (or stdin via `--native-evidence -`). Without native
evidence it reports `status: unverified`, never converged. Native evidence must
be output from the read-only `manifest reconcile --json` path; that command may
resolve a release source, so do not run it if network-free inspection is required.
This script itself performs no network calls, installation, authentication, or
mutation.

The result includes `status`, `drift[]`, `harnesses` with separate receipt and
observed fields, `native_observed`, `authentication: not_tested`, and
`repair_required`. Missing/malformed/empty receipts, absent selected native
registrations, unverified observations, or drift are non-success. Unselected
harnesses are informational. If repair is required, point the user to the
installation documentation's explicit `uvx` repair command. Do not infer
authorization to repair from an audit request.

## Sub-agent dispatch

Follow the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
The parent compares independently collected harness inventories directly.
