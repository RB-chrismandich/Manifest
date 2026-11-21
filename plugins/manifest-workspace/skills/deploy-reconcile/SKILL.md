---
name: deploy-reconcile
description: Compare Manifest installation receipts, portable bundle contracts, and harness-native inventories; report structured drift and whether an explicit repair is required.
---

# Plugin Reconcile

Run `scripts/plugin_reconcile.py --json`. The command is analysis-only and
reads `$XDG_STATE_HOME/manifest/installation.json`; it never calls bootstrap,
an ephemeral coordinator, or mutates an installed harness.

The result includes `status`, `drift[]`, `receipt`, `repair_required`, and
`unverified[]`. Each drift item names the harness and missing, extra, stale,
or disabled capability. Receipt-only agreement is never convergence.

For OMP, run `scripts/plugin_reconcile.py --json --harness omp --inspect-omp`.
The bundled producer uses Python 3.11+ and `omp plugin list --json`, cross-checking
local marketplace catalogs, installed registry, runtime lock, and package links.
It requires no repository checkout, coordinator, package manager, or network.
It only supports the default user profile and local Manifest marketplace;
missing, malformed, conflicting, disabled, or stale evidence stays fail-closed.
Project/profile overrides, npm packages, and other marketplaces are unsupported.

To export the same typed report, run `python3 scripts/omp_native_inspection.py`.
Its stdout feeds `--native-inspection PATH` (or `-` for stdin). Neither command
writes receipts or changes OMP state. The producer is an exact checked mirror of
the repository read-only OMP inventory package; when developing in a full
checkout, regenerate it with the repository inventory generator and verify with
`--check`.

OMP 18.20 exposes no supported CLI component resolver. The report therefore
marks package components unobserved and always uses `activation=not-observed`.
Package/cache agreement is not live activation: a successful inventory still
leaves reconciliation `degraded`/unverified. Do not claim convergence from
receipts, cached files, or synthetic fixtures. Issue #1030's activation boundary
remains unqualified; compatibility readiness is not native inspection evidence.
If repair is
required, point the user to the installation documentation's explicit `uvx`
repair command. Do not infer authorization to repair from an audit request.

## Sub-agent dispatch

Follow the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
The parent compares independently collected harness inventories directly.
