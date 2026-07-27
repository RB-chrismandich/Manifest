# Constitution v2.0.0 vs the Shipped State

**Produced by**: T035 (Constitution I/V) · **Checked**: 2026-07-27
**Result**: ⛔ **INCONSISTENT — two Principle V properties are violated by the
adopted mechanism.** Both must be resolved before Phase 3, and one of them
cannot be resolved by writing code.

Constitution v2.0.0 was authored *by this feature* (source line: "Source:
specs/522-apm-deploy-migration"). It was written before the spike measured what
apm actually does. The spike then measured behaviour that contradicts it, and
FR-034 was rewritten to match the measurement — which moved the conflict out of
the spec and into a contradiction with the constitution rather than resolving it.

## ⛔ V.4 — User-edit preservation

**Constitution V.4 (MUST)**: "a deployed file the user has modified MUST NOT be
silently overwritten; it MUST be preserved and reported."

**Measured (T005, both install modes)**: apm **silently overwrites** the edit.
`apm audit` cannot report it — `drift.py` implements ref, orphan, config-MCP and
stale-file drift, and deployed-file *content* drift is not a category.

**FR-034 as amended**: "hand-edits … MAY be silently overwritten."

**Adopting apm as the deploy mechanism violates a constitutional MUST.** FR-034's
rewrite is a spec change; it has no authority over the constitution.

Note precisely what is and is not available:

| Property V.4 requires | apm | Manifest-side workaround |
|---|---|---|
| **Preserved** (not overwritten) | ❌ no | ❌ none — apm overwrites during install; nothing can intercept |
| **Reported** | ❌ no | ⚠️ possible — FR-034(d)'s re-hash against `deployed_file_hashes` |

So even the fullest Manifest-side guard buys *reported*, never *preserved*. V.4
requires both.

**This needs a decision, not an implementation:**

- **(a) Amend the constitution.** Scope V.4 to mechanisms that can express it, or
  replace "preserved" with "detected and reported" and accept build-output
  semantics. This is the honest option if deployed trees really are build
  outputs — which is what FR-034 now asserts.
- **(b) Abandon apm as the deploy mechanism** and keep the homegrown
  hash-manifest deployer the decision record names as the fallback. It can
  satisfy V.4 because Manifest controls the write.
- **(c) Declare a scoped, time-boxed exception**, recorded in the constitution
  rather than left implicit.

Doing nothing is not neutral: it ships a mechanism that violates a MUST while the
constitution still claims the property holds.

## ⛔ V.3 — Orphan removal without a separate pass

**Constitution V.3 (MUST)**: an orphaned file "MUST be removed by the deploy
itself, **not by a separate reconciliation pass**."

**Shipped state** (`migration-inventory.md`): the 170 script files stay on the
legacy rsync pipeline, which keeps no ownership record, so
`deploy_reconcile.sh` — a separate reconciliation pass — **cannot be retired**.

V.3 holds for migrated domains (apm's lockfile removes what a package no longer
produces) and fails for everything still on rsync. The constitution states V.3 as
a property of *every* deploy mechanism, not of the migrated subset.

**Resolution options**: migrate scripts (blocked — APM's target model has no
notion of a `PATH` install with relative siblings), give the legacy deployer its
own ownership manifest, or scope V.3 explicitly to managed domains and record
that scripts are out of scope.

## ✅ What is consistent

- **V.1 Identical output** — apm reinstalls byte-identically from the same source.
- **V.2 Idempotence** — measured: re-install is byte-identical, both install modes.
- **V.5 Single ownership** — this is what the domain registry and gating enforce,
  and `apm_ownership_report.sh` detects violations in both directions. The Phase 2
  zero-owner window is not a V.5 violation (V.5 forbids *two* writers), though it
  is why T053's escape hatch is mandatory.
- **V.6 Fail closed** — the binary gate, the publish gates and the install verifier
  all reject rather than degrade, with regression tests asserting each.
- **VII Published Artifact Integrity** — version pinning, lockfile reproducibility,
  integrity verification, pre-publish scrubbing and an offline path all exist.
- **Principle I** — no longer names a mechanism, so changing deployers no longer
  contradicts it by construction. That amendment did its job.

## On the `--reconfigure` guidance T035 also asks about

Checked `CLAUDE.md`, `configs/claude/CLAUDE.md`, `docs/CONFIGURATION.md`,
`docs/GETTING_STARTED.md`. **No stale drift-correction guidance remains** — every
surviving `--reconfigure` mention is legitimate service-toggle usage
(`--reconfigure --disable-cursor` and similar), not a claim that it corrects
drift. The v2.0.0 amendment already removed that claim from Principle I, and
`docs/DEPLOY_OWNERSHIP.md` now documents the real drift path
(`apm_ownership_report.sh` to detect, `apm_ungate_domain.sh` to correct).

Nothing to update here; recorded so the check is not repeated.
