---
name: deploy-reconcile
description: Compare Manifest installation receipts, portable bundle contracts, and harness-native inventories; report structured drift and whether an explicit repair is required.
---

# Plugin Reconcile

Run `scripts/plugin_reconcile.py --json`. By default the command compares a strictly validated installation receipt
with independently obtained native evidence from the receipt-bound, bundle-local observer. An explicit
`--receipt PATH` selects the exact receipt. `--native-evidence PATH` (or `-` for stdin) accepts saved
`manifest reconcile --json` evidence without a harness filter. `--native-inspection PATH` (or `-`) accepts
typed portable inspection evidence and supports `--harness`. These evidence sources are mutually exclusive.
Without readable evidence the result is degraded/unverified, never converged. The command never calls bootstrap,
an ephemeral coordinator, or mutates an installed harness. It performs no network calls, installation,
or authentication.

For OMP, run `scripts/plugin_reconcile.py --json --harness omp --inspect-omp`. The bundled producer uses Python
3.11+ and `omp plugin list --json`, cross-checking local marketplace catalogs, installed registry, runtime lock,
and package links. It requires no repository checkout, coordinator, package manager, or network. It only supports
the default user profile and local Manifest marketplace; missing, malformed, conflicting, disabled, or stale
evidence stays fail-closed. Project/profile overrides, npm packages, and other marketplaces are unsupported.

To export the same typed report, run `python3 scripts/omp_native_inspection.py`. Its stdout feeds
`--native-inspection PATH` (or `-` for stdin). Neither command writes receipts or changes OMP state. The producer
is an exact checked mirror of `src/manifest_agent/omp_readonly`; from a repository checkout, maintain the mirror
with the repository-level inventory generator and verify it in check mode.

OMP 18.20 exposes no supported CLI component resolver. The report therefore marks package components unobserved and
always uses `activation=not-observed`. Package/cache agreement is not live activation: a successful inventory
still leaves reconciliation degraded and unverified. Do not claim convergence from receipts, cached files, or
synthetic fixtures. Issue #1030's activation boundary remains unqualified; compatibility readiness is not native
inspection evidence.

The result includes status, drift, receipt, repair-required, and unverified evidence; the native-evidence path
additionally preserves the established receipt/observation fields. Missing, malformed, or empty receipts, unknown
or unobserved activation, absent selected native registrations, unverified observations, or drift are non-success.
Unselected harnesses are informational. The reconciliation command never provisions an observer; if its selected
receipt has no usable prepared runtime, report the explicit observation failure and direct the user to authorized
install/update. If repair is required, point the user to the installation documentation's explicit `uvx` repair
command. Do not infer authorization to repair from an audit request.

## Sub-agent dispatch

Follow the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
The parent compares independently collected harness inventories directly.
