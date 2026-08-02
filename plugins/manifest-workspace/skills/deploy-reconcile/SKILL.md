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
