# Success Criteria Validation

**Produced by**: T047 · **Validated**: 2026-07-27
**Scope**: Phases 0–3 as shipped. US2/US4 criteria are reported against the
measured blockers, not deferred silently.

Each criterion carries the command that produced its verdict, so a reader can
re-run it rather than trust this table.

| SC | Verdict | Evidence |
|---|---|---|
| **SC-001** reproduce from published package + lockfile | ✅ **MET** | `bats tests/bats/apm_deploy_isolated.bats` → FR-004 case: 108 skills from `apm install 'RB-chrismandich/Manifest#v0.0.0-apm-preview.1'`, non-empty asserted |
| **SC-002** rename leaves zero orphans | ✅ **MET** | same suite, FR-006 case — asserts old path **present** first, then absent after rename |
| **SC-003** user-modified file survives + is surfaced | ⚠️ **AMENDED** | Constitution v3.0.0 changed the underlying rule from preserve to **detect**. Survival is not achievable — apm performs the write. Detection is: `configs/claude/scripts/apm_drift_report.sh` → `MODIFIED …` with both hashes. See `constitution-consistency.md` |
| **SC-004** two deploys byte-identical | ✅ **MET** | same suite, FR-005 case — tree hash before/after, equality asserted |
| **SC-005** exactly four scripts deleted | ⛔ **VOID** | Measured: apm emits **0** `.mdc` files for a 108-skill package; the generators have no replacement. Deleting them destroys capability. See `us2-blocked.md` |
| **SC-006** bootstrap deploys zero content for migrated domains | ⚠️ **NOT YET EXERCISED** | The mechanism is built and tested (`apm_ownership_boundary.bats`, 13/13, asserts **zero** live writers under a gated registry) but the live registry is `domains: []`, so no domain is migrated in production yet |
| **SC-007** 100% of deploy verification uses an isolated HOME | ✅ **MET** | `bats tests/bats/apm_isolation_sentinel.bats` — 7 cases incl. a control proving the check can fail, and a runtime bound so it stays runnable per-test |
| **SC-008** each drift class has a regression test | ✅ **MET** | `apm_deploy_isolated.bats` header maps each named historical instance (mcpServers clobber, `__pycache__` orphan, unpruned cursor rules, toggle-off copy) to the case generalizing it |
| **SC-009** spike returns GO/NO-GO naming the version | ✅ **MET** | `decision-record.md` — GO, `apm` v0.26.0, per-primitive results, control case recorded |
| **SC-010** plugin names carry `manifest-` prefix | ⏸️ **N/A** | US4 not implemented; `plugin-partition.md` records the analysis and the unmeasured plugin-to-plugin dependency assumption it rests on |
| **SC-011** zero publishes without a preceding gate record | ✅ **MET** | Two publishes in history, two gate records, both preceding: spike `17:43:16Z` → repo `17:43:24Z`; release `23:11:33Z` → tag push. `tail -2 gate-records.jsonl` |

## Summary

**8 met, 1 amended, 1 void, 1 N/A.**

The two that did not survive contact with measurement are the two the spec was
most confident about:

- **SC-003** assumed a deployer that preserves user edits. No package manager
  does; the constitution was amended to require detection, and detection was
  built.
- **SC-005** assumed the cursor generators were replaceable. They are not —
  apm has no instructions target, so there is nothing to replace them with.

Neither is a shortfall in execution. Both are cases where the criterion encoded
an assumption about the tool that the tool does not satisfy, and the honest
close is to say so rather than to restate the criterion until it passes.

**SC-006 was activated 2026-07-28** and is now met. The order used on the live
machine was **deploy first, then gate** — the reverse of the phase plan, and
deliberately so: gating first leaves the domain writer-less in between, which on
a repo branch is a documented window and on a running machine is skills silently
not updating. A brief double-claim is the safer failure of the two.

One adoption blocker surfaced and is worth knowing: apm **skipped**
`ai-hooks-integration` on the first pass — the deployed copy carried 10 local
build artifacts (`.pytest_cache`, two `__pycache__`) from running that skill's
tests, and apm declines to adopt a directory holding files it did not place.
Removing the regenerable artifacts and re-installing took it to 108/108. Had the
gate been flipped before noticing, that one skill would have been owned by
neither pipeline.
