# Decision Record — Feature 522 (APM deploy-pipeline migration)

Created by T050 (Phase 0, publish-gate slice). Only **Threat controls** is
populated here — it is required before the spike may publish anything
(FR-018). Every other section is a placeholder for the spike's own output
and is intentionally out of scope for this run.

## Decision

_pending T006_

## Matrix results

_pending T006_

## Assumption cells

_pending T006_

## Threat controls

Concrete enforcing mechanism per threat (FR-018). Each is independent of
which registry model T005 ends up measuring (git-host or registry-protocol
server), and none trusts the `apm` binary's own supply-chain claims —
`apm`'s native capability is unmeasured before T005, so nothing here relies
on it.

- **Typosquatting** (installing a similarly-named but different package):
  enforced by **name-pinned install + independent hash verification**.
  `configs/claude/scripts/apm_install_verify.sh verify TREE --ref REF`
  recomputes the canonical content hash of whatever was actually fetched and
  accepts it only if it matches the single `result:"pass"` gate record for
  the exact `REF` requested. A typosquat package is different bytes under a
  similar name; it has no gate record for the ref the installer asked for,
  so it fails closed regardless of how convincing the package name is.
- **Dependency confusion** (a same-named package served from an
  unintended/attacker-controlled registry instead of the intended one):
  enforced by **single-registry pin + independent hash verification**. The
  install path is expected to resolve exactly one named registry/source, and
  `apm_install_verify.sh` re-hashes the fetched tree regardless of which
  registry actually served it. A confused resolution either violates the
  pin outright, or — if it doesn't — still has to produce bytes matching the
  hash recorded for the legitimate publish, which an unintended source
  cannot do without also compromising that publish's provenance.
- **Registry-account compromise** (an attacker publishes a malicious
  version under the legitimate maintainer's account): enforced because
  `configs/claude/scripts/apm_publish_gate.sh all` only records a
  `subject_sha256` for a tree that also passed `apm_publish_gate.sh
  provenance` (T049/FR-038) — a clean working tree at a tagged commit. A
  compromised registry account can push arbitrary bytes to the registry, but
  cannot retroactively produce a matching `result:"pass"` gate record for
  those bytes without also compromising the source repository and its tag.
  `apm_install_verify.sh` rejects the mismatch at install regardless of what
  the registry itself will serve.

## Control case

_pending T006_

## Evidence

_pending T006_
