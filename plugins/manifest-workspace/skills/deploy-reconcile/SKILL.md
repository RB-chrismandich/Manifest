---
name: deploy-reconcile
description: Compare Manifest installation receipts, portable bundle contracts, and harness-native inventories; report structured drift and whether an explicit repair is required.
---

# Plugin Reconcile

Run `scripts/plugin_reconcile.py --json`. The command is analysis-only and
reads `$XDG_STATE_HOME/manifest/installation.json`; it never calls bootstrap or
the ephemeral coordinator and never mutates an installed harness.

The result includes `status`, `drift[]`, `receipt`, and `repair_required`. Each
drift item names the harness and missing or mismatched capability. If repair is
required, point the user to the installation documentation's explicit `uvx`
repair command. Do not infer authorization to repair from an audit request.

## Sub-agent dispatch

This skill uses the shared OMP dispatch contract in
`../../runtime/references/sub-agent-dispatch.md`: submit all ready independent
units in one `task` call, in waves of at most 32; children execute directly and
never redispatch; use `hub` only to coordinate or wait; and the parent validates
and aggregates evidence. If `task` is unavailable, work inline and report
`DEGRADED`.

**Policy: conditional.** When drift spans multiple independent harness
inventories, dispatch those read-only comparisons together in one OMP `task`
call (waves of at most 32), using `scout`. Children execute only their assigned
inventory comparison and never redispatch. The parent uses `hub` only to
coordinate or wait, validates and aggregates the evidence directly, and does
not use text-consensus or synthesis. If `task` is unavailable, compare inline
and report `DEGRADED`; never fall back to a provider CLI.
