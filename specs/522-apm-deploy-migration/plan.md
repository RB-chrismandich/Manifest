# Implementation Plan: APM-Based Deploy Pipeline (Drift Elimination)

**Branch**: `522-apm-deploy-migration` | **Date**: 2026-07-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/522-apm-deploy-migration/spec.md`

**Revision**: v2, after five adversarial reviews (four independent critics + the parallel-agent panel). Two BLOCKERs, six HIGHs, and a set of factual corrections were folded in; the changes are itemized in [Review Response](#review-response).

## Summary

Adopt Microsoft APM (Agent Package Manager) as Manifest's build and deploy layer for configuration content, so each assistant home becomes a reproducible, hash-tracked build output instead of accumulated state. `bootstrap.sh` narrows to CLI installation, authentication, MCP configuration, service toggles, and the settings merge. Distribution is **publish-and-install** (maintainer decision): Manifest is published as a package and installed by name, which makes integrity verification, pre-publish scrubbing, an offline path, and a publish-free local dev loop mandatory rather than optional.

The work is **gated on a feasibility spike** whose NO-GO terminates the feature with a decision record and no source changes. Migration is **parallel-run**, but with a correction from review: every legacy writer of a domain is gated off it **before** that domain's first APM deploy, not three phases later. Optional US4 packages the Claude-facing slice as compartmentalized `manifest-` plugins.

## Technical Context

**Language/Version**: Bash (bootstrap + scripts), Python 3.11+ (generators, config, tests), YAML/JSON (manifests)

**Primary Dependencies**: `apm` CLI pinned at **v0.26.0** (published 2026-07-18) — new external dependency on the critical path, **and itself a code-execution risk surface** (see E8); existing: `git`, `rsync`, `pre-commit`, `bats-core`, `pytest`, `shellcheck`, `yamllint`

**Storage**: Filesystem — repo source tree, `apm.lock.yaml`, five assistant home trees, plus a package registry under the published model

**Testing**: `bats` (deploy behavior, isolated `HOME`), `pytest` (Python), pre-commit changed-file gate with `--from-ref origin/main`

**Target Platform**: macOS (Intel + Apple Silicon), Linux (Debian/Ubuntu, RHEL/Fedora, Arch, openSUSE)

**Project Type**: Configuration distribution system / CLI tooling

**Constraints**: Zero double-written paths at every step; all deploy verification in an isolated `HOME` with isolation itself asserted; version-pinned pre-1.0 dependency; remote resolution inherent under the published model

**Scale/Scope** *(corrected — the first draft mislabeled directory-entry counts)*: **107** skills, **54** top-level scripts (**88** including subdirectories), **109** committed `.mdc` artifacts, 5 assistant homes, 4 retiring scripts + 1 explicitly retained + 1 reclassified as a deployer

### Verified external findings (evidence basis)

Checked against primary sources 2026-07-25 and re-checked under adversarial review. **The spike re-verifies the load-bearing ones empirically; none are accepted as evidence on their own.**

| # | Finding | Confidence | Consequence |
|---|---|---|---|
| E1 | Install performs stale-file cleanup gated by **per-file content hashes in the lockfile**; edited files are **retained** | Hash/cleanup: **confirmed**. "Warned at install time": **OPEN** — docs describe retained files as surfaced by a *separate* `apm audit --ci`, not necessarily an inline install warning | Satisfies FR-004. FR-005 requires surfacing *in the deploy workflow*, so if retention is silent at install the audit step must be wired into the deploy path. Spike must measure this |
| E2 | `--target` accepts `copilot, claude, cursor, opencode, codex, gemini, antigravity, windsurf, kiro, intellij, vscode, agent-skills`; `all` **excludes** `agent-skills`, `antigravity`, `intellij` | Confirmed | Antigravity must be **named explicitly** (FR-011) |
| E3 | `--global` installs to `~/.apm/`; local `.apm/` deployment is **skipped** at `--global` | Confirmed, and **unambiguous** | Reframed: the docs are clear, so the risk is **doc/behavior mismatch on a pre-1.0 tool**, not textual ambiguity. This is also *why* publish-and-install is the coherent model — it is the documented-working path |
| E4 | `apm audit` detects drift | Confirmed | Supersedes `deploy_reconcile.sh` (FR-008) — but see E9 |
| E5 | `apm pack` bundles a package as a zipped artifact **or a plugin** | Confirmed | Makes US4 a downstream artifact of the same source |
| E6 | Plugin `settings.json` supports **only** `agent` and `subagentStatusLine`; plugin agents cannot declare `hooks`/`mcpServers`/`permissionMode`; marketplace entry name keys `enabledPlugins` and `/plugin` | Confirmed verbatim. **Nuance**: component *namespacing* is documented as driven by `plugin.json`'s `name`; that a differing marketplace name overrides it for namespacing is **not** stated | Bounds US4 (FR-024). FR-026's "prefix both" stands as belt-and-braces, not as a proven three-way equivalence |
| E7 | Repo created 2025-09-18, 3,368 stars, 159 open issues, ~weekly releases, pre-1.0 | Metrics confirmed exactly. The earlier "one issue closed within two days" claim was **uncited and is withdrawn** as evidence | Pin the version (FR-017); treat maintenance signals as motivating context only |
| E8 | *(new)* Deployed hooks execute shell commands; deployed MCP entries spawn processes with tool access. The `apm` binary writes both, into five home trees | Confirmed from the harness's own hooks/MCP references | The trust surface is **not** limited to remotely-resolved packages: the tool binary itself needs integrity verification (FR-029) |
| E9 | *(new)* `apm.lock.yaml` is generated by `apm`; `apm audit` reads it back | Structural | Lockfile + audit are **one trusted party checking its own work**. An independent tree hash is required as a standing gate (FR-036) |
| E10 | *(new)* The tool's own target matrix states **no target generates catalog/documentation indexes** beyond `AGENTS.md`-style guides | Confirmed | `generate_commands_doc.py` has **no equivalent** and stays on the legacy pipeline (FR-037). SC-005 corrected from "at least five" to exactly four |

### Verified repository findings

| # | Finding | Consequence |
|---|---|---|
| R1 | `deploy_home_skills()` (`bootstrap/lib/common.sh`) writes `~/.claude/skills` on every `./bootstrap.sh`; `sync-skills.sh` (installed to `~/.local/bin`) writes the same paths and is the documented **daily** skill-dev workflow | **BLOCKER as originally sequenced.** The MVP domain already has two writers; gating must precede the first APM deploy (FR-027) |
| R2 | `link_shared_assets()` symlinks four harnesses' skill dirs to `~/.claude/skills` — one copy, four consumers | Conflicts with per-target compiled output; must be decided explicitly (FR-033) |
| R3 | `install_issue_hooks.sh` mutates the **deployed** `command_config.yml`; `preserve_issue_sync_gates()` exists to carry that across redeploys | Scripted mutation would look like a permanent hand-edit under user-edit retention (FR-034) |
| R4 | `git_ops.sh` is invoked by 12 skills spanning four proposed plugin domains; `git_platform.sh` spans two | Compartmentalization must handle the shared-script graph or be cosmetic (FR-028) |
| R5 | `configs/claude/scripts/config.py` does **not** exist; the real file is `configs/claude/scripts/agents/config.py`, and its constructors already accept `config_path` | The prerequisite shrinks to wiring a flag/env var to an existing parameter |
| R6 | `deploy_configs()` is monolithic — no per-domain selector | FR-019's rollback needs a selective-deploy capability built, not just documented |
| R7 | ~~`test-isolate-ambient` exists only in the deployed home, not in committed source~~ — **RESOLVED** by merging `origin/main` (PR #622) on 2026-07-25, which committed the skill to `.retired skill supply/skills/` | Tasks may now cite it as an isolation handle; a fresh clone and CI can follow them. Re-verify before Phase 0 rather than trusting this row |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**The constitution was amended to v2.0.0 as part of this work** (`.specify/memory/constitution.md`). The amendment is deliberately **mechanism-neutral** — it names no package manager and presupposes no spike outcome, so it is valid under GO or NO-GO and is not an implicit adoption decision.

| Principle | Status | Notes |
|---|---|---|
| **I. Configuration-as-Code** *(redefined)* | ✅ Satisfied | Was mechanism-named (`bootstrap.sh`, `--reconfigure`), which made *any* deployer change a constitutional violation by construction. Now property-first: version-controlled source, reproducible-from-manifest deploy, single-owner paths, detectable and correctable drift. Adds that a *preserved* user edit must surface as drift — closing the quiet-drift hole. |
| **II. Parallel Agent Orchestration** | ✅ Satisfied | Architectural + >200 lines → cross-verification required. Five reviews run on these artifacts. **Note**: the panel returned consensus 0.00 because two of four agents failed on environment errors (tier ineligibility; workspace-trust prompt) — a false BLOCKED, judged on completed agents plus substantive findings, as the known failure mode prescribes. |
| **III. Consensus-Driven Decisions** | ✅ Satisfied | Verdicts use APPROVED/NEEDS_REVIEW/BLOCKED with the caveat above. |
| **IV. Skill-First Extensibility** | ✅ Satisfied | Delivery change, not capability change. Skills move to `.apm/skills` as the sole source of truth (FR-021a, amended 2026-07-27); the catalog itself is unchanged. |
| **V. Reproducible, Idempotent Deployment** *(redefined)* | ✅ Satisfied | Widened from one script to *every* deploy mechanism, and raised: byte-identical no-change re-runs, orphan removal, user-edit preservation, **single ownership**, fail-closed. FR-014/FR-027 implement property 5 directly. |
| **VI. State-Gated Lifecycle** | ✅ Satisfied | Running in order; Verify gate backed by the deploy smoke suite; FR-023 requires a per-property regression test with asserted preconditions. |
| **VII. Published Artifact Integrity** *(new)* | ⚠️ Binding | Activated by the publish-and-install decision. Provenance, pinning, integrity, pre-publish scrubbing, offline path, and a publish-free local dev loop are now constitutional requirements, implemented by FR-018 and FR-029 – FR-032. |

**Gate result**: Proceed. The constitutional tension the first draft flagged is resolved by amendment rather than deferred.

## Project Structure

### Documentation (this feature)

```text
specs/522-apm-deploy-migration/
├── spec.md              # Feature specification (v2)
├── plan.md              # This file (v2)
├── tasks.md             # Task breakdown (v2)
├── decision-record.md   # Spike GO/NO-GO — gates everything after Phase 0
└── migration-inventory.md  # Domain classification + skill→plugin map + shared-script graph
```

### Source Code (repository root)

```text
.apm/                                  # NEW — single source primitive tree (post-GO)
├── skills/                            # view of .retired skill supply/skills — never a copy (FR-021)
├── agents/  hooks/  instructions/  context/
apm.yml                                # NEW — package manifest (pinned tool version, explicit targets)
apm.lock.yaml                          # NEW — committed lockfile: resolved tree + per-file hashes

configs/                               # EXISTING — shrinks as domains migrate
├── claude/scripts/                    # 54 top-level (88 recursive) — FR-020 decision
│   ├── agents/config.py               # already parameterized; wire flag/env (R5)
│   ├── generate_commands_doc.py       # RETAINED — no equivalent (FR-037, E10)
│   └── sync-skills.sh                 # RECLASSIFIED — a deployer, gated per-domain (FR-027)
└── cursor/rules/*.mdc                 # 109 derived artifacts — DELETED in US2

bootstrap.sh / bootstrap/lib/
├── common.sh    deploy_home_skills() + link_shared_assets()  # gated per-domain (FR-027, FR-033)
└── deploy.sh    deploy_configs()                             # gains per-domain selector (FR-019, R6)

RETIRED in US2 — exactly four (SC-005), each only after two clean equivalence runs:
  generate_cursor_rules.sh · generate_cursor_agents.py · generate_cursor_mcp.py · deploy_reconcile.sh

plugins/                               # US4 only — generated output of `apm pack`
└── .claude-plugin/marketplace.json    # every entry prefixed manifest- (FR-026)

tests/bats/
├── apm_deploy_isolated.bats           # FR-004..FR-007, preconditions asserted (FR-023)
├── apm_isolation_sentinel.bats        # FR-035a — real HOME unchanged after sandboxed runs
├── apm_ownership_boundary.bats        # FR-014/FR-027 — one writer per path
├── apm_supply_chain.bats              # FR-018/FR-029 — integrity gates, enforced not inspected
└── manifest_plugin_naming.bats             # US4 — prefix + partition + functional partial enablement
```

**Structure Decision**: Additive-then-subtractive. `.apm/` is added alongside the
existing pipeline; `configs/` and `bootstrap/lib/` shrink only as each domain is
proven equivalent **and its legacy writers are gated**.

~~`.retired skill supply/skills` remains the physical source of truth; `.apm/skills` is a
view, never a copy.~~ **AMENDED 2026-07-27 (FR-021a)**: `.apm/skills` becomes
the sole physical source of truth and `.retired skill supply/` is removed. The
view-never-a-copy rule existed to avoid a third skill location while retired skill supply
stayed authoritative; with retired skill supply deprecated there are two locations during
the migration and one after, so the rule is replaced by FR-021a's stricter
invariant: **no shipped commit may leave two authoritative skill trees**.

### Plugin compartmentalization (US4) — status: **hypothesis invalidated, redesign required**

The first draft proposed ten domains by name-prefix. Review demonstrated the heuristic fails against the real catalog:

- **Direct collisions**: `a11y-audit` matches both `*-audit` (`manifest-security`) and the `manifest-design` list; `config-audit` matches both `config-*` (`manifest-deploy`) and `*-audit` (`manifest-security`).
- **Semantic misplacement**: `pr-smoke` matches `pr-*` (`manifest-git`) but functionally belongs to `manifest-test`.
- **Unmapped**: roughly **25 of 107** skills match none of the ten patterns as written.
- **Hidden coupling**: `git_ops.sh` is invoked by 12 skills across four of the proposed domains, `git_platform.sh` across two — so a name-based partition does not produce independently functional plugins (R4).

The ten names are retained only as a **starting vocabulary**. The authoritative map must come from functional analysis plus the shared-script dependency graph (FR-025, FR-028), and the partition must be asserted by test, not by inspection.

## Phasing

| Phase | Gate to exit |
|---|---|
| **0 — Publish gates + Spike** | Blocking content scan, provenance gate, and install-integrity verification exist **before** anything is published (T048–T050). Then: decision record with GO/NO-GO, **per-primitive-type** results, tool version, rig validated by sentinel + control case. **NO-GO ends the feature.** |
| **1 — Prerequisites** | Config lookup parameterized; isolated-`HOME` harness with asserted isolation; ownership diagnostic **built before the coexistence window**; migration inventory written; per-domain selective deploy exists |
| **2 — Gate legacy writers** | Every legacy writer of the MVP domain is gated off it, verified by the ownership test. **This precedes any APM deploy of that domain** |
| **3 — US1 (MVP)** | One domain, one harness: four drift properties pass in isolated `HOME`, each with asserted preconditions |
| **4 — US2** | All five harnesses from one source; full CI mirror green **before** deletion; each generator deleted only after two independent clean runs plus one functional consumption check; 109 `.mdc` untracked |
| **5 — US3** | `bootstrap.sh` owns zero config content for migrated domains; rollback proven |
| **6 — US4 (optional)** | Functional domain map; `manifest-` plugins; partition, naming, and partial-enablement **function** verified |
| **7 — Polish** | Publish gates regression-proofed (T042); SC-011 verified across all publishes (T043); offline + local-dev paths; upgrade gate; FR-001 and full SC validation |

Ordering changes, all review- or analysis-driven: gating moved *before* the first APM deploy (was Phase 4); the ownership diagnostic moved *before* the coexistence window (was after); the full CI mirror moved *before* the irreversible deletions (was last); and — from the analyze pass — the **publish gates moved from Phase 7 to Phase 0**, because the spike publishes a real package to a real registry and publication is irreversible.

## Risk & Rollback

| Risk | Mitigation |
|---|---|
| Spike NO-GO after effort spent | Spike is first, time-boxed to two working days, touches no Manifest source |
| **False NO-GO from rig error** | Known-good control case the rig must detect before a NO-GO is trusted (FR-035b) |
| **Isolation silently fails; every result invalid** | Sentinel check: real `~/.claude` hash-identical before/after each sandboxed run (FR-035a) |
| **Legacy writer clobbers APM-owned files** | Gating precedes first deploy (FR-027); ownership test re-run at every step including first dual-live moment |
| Pre-1.0 breaking change | Pinned version; upgrade re-runs equivalence + idempotence via an enforcing gate (FR-017) |
| **Malicious release under the pinned tag / compromised binary** | Tool binary install channel integrity-verified independently of resolved packages (FR-029) |
| **Lockfile and audit are the same trusted party** | Independent tree hash as a standing CI gate (FR-036) |
| Registry attacks (typosquat, dependency confusion, account compromise) | Explicit controls specified and gated automatically (FR-018) |
| Secrets published irreversibly | Blocking pre-publish scan (FR-030) |
| Registry/network outage blocks provisioning | Pinned local artifact install path (FR-031) |
| Iteration becomes distribution | Publish-free local dev loop (FR-032) |
| Partially migrated machine left broken | Per-domain selective deploy built in Phase 1, then proven (FR-019, R6) |
| Documentation-index generation has no equivalent | Stated, retained on legacy pipeline, excluded from SC-005 (FR-037) |

**Rollback position**: Until Phase 4 deletes a generator, every step is reversible by not running the new pipeline. The first irreversible acts are **deleting a generator** and **publishing a package** — the latter newly irreversible under the publish model, which is why FR-030's scan blocks rather than warns.

## Complexity Tracking

> Constitution violations were resolved by amendment (v2.0.0) rather than left outstanding. The entries below record the remaining justified complexity.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| A pre-1.0 external tool on the critical path of machine setup | The ownership manifest is the entire point; a stable-but-absent tool solves nothing | **Wait for 1.0**: an indefinite hold on a live, recurring bug class. Risk bounded by pinning, parallel-run, rollback, and a two-day NO-GO exit |
| **Homegrown hash-manifest deployer not chosen** | Adopting a maintained tool avoids owning lockfile semantics, multi-harness compilation, and stale-file reconciliation | **Honest re-assessment after review**: this alternative is *stronger* than v1 claimed. The repo already carries partial attempts (`deploy_reconcile.sh`, `deploy_stamp_check.sh`); a manifest-of-paths-and-hashes deployer is on the order of a few hundred lines, comparable to scripts already maintained here, and avoids a weekly-release dependency with 159 open issues. Weighing against it: APM also supplies multi-harness compilation and packaging, which the homegrown option does not. **It is explicitly the fallback if the spike returns NO-GO**, and the spike is cheap precisely so this comparison stays live |
| Two deploy mechanisms coexist during migration | A big-bang cutover of 5 harnesses and 107 skills has no safe verification point | **Cut over at once**: no way to prove equivalence before deleting the only working pipeline. Coexistence is bounded by FR-014/FR-027 — and, per review, the window is now *narrower* than v1: gating precedes the first APM deploy rather than trailing it by three phases |
| Compartmentalization cannot be purely by plugin | Shared scripts (`git_ops.sh`) couple domains that are nominally independent (R4) | **Name-based partition**: demonstrably fails — two skills match two domains, ~25 match none, and disabling one plugin would break skills in another. Either shared components are placed for partial-enablement correctness, or the coupling is documented as cosmetic (FR-028) |

## Review Response

Changes made in v2, by source finding:

- **BLOCKER (scope/risk)** — MVP domain already had two writers with gating three phases late → new FR-027 and a dedicated Phase 2 that gates legacy writers *before* the first APM deploy.
- **BLOCKER (security/plugin)** — `manifest-` domain split fails its own matching rule (2 collisions, ~25 unmapped) and ignores the shared-script graph → ten-domain split demoted to vocabulary; FR-025 requires functional analysis; new FR-028 for the dependency graph.
- **HIGH (testability)** — isolation never verified for the tool's own writes → FR-035a sentinel check; false-NO-GO risk → FR-035b control case; vacuous-pass risks (empty-vs-empty diff, unasserted rename precondition) → FR-023 precondition rule.
- **HIGH (premise)** — `generate_commands_doc.py` has no equivalent → FR-037, SC-005 corrected to exactly four scripts; wrong counts → corrected throughout; wrong `config.py` path and overstated blocker → R5.
- **HIGH (scope/risk)** — symlink fan-out unresolved → FR-033; `sync-skills.sh` miscategorized → reclassified as a deployer; rollback had no mechanism → per-domain selector built in Phase 1.
- **HIGH (security)** — code-execution threat model absent and binary itself unverified → FR-029, E8; FR-018 unenforced → `apm_supply_chain.bats`; publish model forecloses "no remote deps" → FR-018 rewritten.
- **MEDIUM** — `command_config.yml` scripted mutation vs user edit → FR-034, R3; equivalence "independence" undefined and behavior never checked → FR-010 tightened; audit/lockfile not independent → FR-036, E9; concurrent worktrees → edge case.
- **Panel** — evidentiary-bar inconsistency in Assumptions → corrected; APM acronym collision → disambiguated; SC-005 hedge → exact count; pre-publish scrubbing gap → FR-030.

### Analyze pass (v3)

`/speckit-analyze` found 2 CRITICAL, 4 HIGH, 6 MEDIUM, 2 LOW against 37 FRs / 47 tasks (100% FR coverage, 90% SC). Addressed:

- **CRITICAL — publish before gate**: the spike (T004) and first release (T018) both published, while the blocking scan sat in Phase 7. Publication is irreversible, so this violated Constitution VII.4 at the first publish. → T048–T050 created and moved to Phase 0, blocking T004; FR-030 extended to gate *every* publish including spike packages; new SC-011.
- **CRITICAL — provenance unimplemented**: Constitution VII.1 (tagged version, no dirty-tree publish) had no FR and no task. → new **FR-038**, task T049.
- **HIGH — FR-034 documented but not built** → new task T051, sequenced before any config-YAML migration.
- **HIGH — FR-005 remediation unassigned** → new conditional task T052, gated on T005's measurement, with an explicit "close with evidence, not unexamined" rule.
- **HIGH — SC-008 half-covered** → T017 now enumerates the named historical drift instances in the test file.
- **HIGH — integrity gate after installs begin** → split out of T042 as T050 in Phase 0.
- **MEDIUM** — plan phase table omitted Phase 7 → added; zero-writer window had no escape → new **FR-039** + T053 on the critical path; FR-018's "controls MUST be specified" named its artifact; FR-033 gained four selection criteria; FR-005 aligned to Constitution I's "surface as drift"; 7 tasks gained FR refs.
- **Deliberately not done**: merging the FR-022/FR-035a and FR-018/FR-029 overlaps — renumbering would break 47 task references, so both pairs were **scope-clarified** in place instead. Branch creation (`522-apm-deploy-migration`) is left to the user: switching HEAD would move the active worktree out from under the session.
- **Self-correction (v3)**: adding pre-GO publish gates contradicted FR-001 ("no source modified before GO"). Rather than leave the conflict, FR-001 gained one narrow, justified carve-out — additive, self-contained, valuable under NO-GO — with the verification task asserting nothing else claims it.

### Technical spec-review pass (v4)

`/spec-review --mode technical` (parallel-agent panel, Claude excluded as author) returned 7 findings against 39 FRs / 53 tasks. Six were confirmed against the artifacts and applied; no new FRs were needed — every fix attaches to an FR that already existed but had no implementing or gating task. **No task IDs were renumbered** (the v3 constraint holds: renumbering breaks ~50 references), so the two new tasks are T054–T055, placed by phase.

- **HIGH — FR-029 tested but never implemented**: T001 *recorded* the `apm` binary checksum and T042 *asserted* the gate fails closed, but no task made `bootstrap.sh` download and verify the binary. A test with no subject. → new **T054** (Phase 1), fail-closed, distinct from T050's *package* verification; T042 and the critical path updated.
- **HIGH — contributor dead zone, Phases 2–6**: T015 gated `sync-skills.sh` in Phase 2 while its replacement, the publish-free local loop (FR-032), sat in T044 in Phase 7 — leaving a registry publish as the only way to test a one-line skill edit for four phases, and putting FR-021 and FR-027 in direct conflict. → new **T055**, sequenced *before* T014/T015; T044 keeps the offline path only; T015's skip message must name the replacement command.
- **HIGH — structural blockers measured after the gate that they should inform**: the spike settled deploy mechanics but deferred three assumptions the GO rests on. → T005 gains cell **(d)** publish-free loop, **(i)** symlinked-target behavior against the real fan-out, **(ii)** installer-written vs human mutation; T006 must record a GO/NO-GO input for each, where *not measured is a NO-GO for that cell*. T013 and T051 now consume that evidence instead of re-discovering it.
- **MEDIUM — rollback restored the writer but not the ownership**: T053 returned a domain to the legacy writer, which overwrites only the paths it knows about — anything APM added survives as an orphan owned by neither pipeline, i.e. the untracked-hybrid state this feature exists to remove. → T053 gains a reclamation step plus an ownership-boundary assertion; T034 proves it by diffing against a never-migrated tree.
- **LOW (conditional) — `generate_commands_doc.py` coupling**: verified the generator resolves its catalog from `_REPO_ROOT / .retired skill supply/skills` (override: `COMMAND_CATALOG_SKILLS_DIR`) — the *repo* source of truth, not a deployed home — so the migration alone cannot break it. The panel's proposed verification step was heavier than the risk. → T029 gains a one-line conditional tied to T013 changing the repo-side path.
- **Panel finding not applied as written**: the FR-034 and FR-032 findings were filed separately from the symlink one; all three share a single root cause (a feasibility gate that did not gate everything downstream of it), so they were applied as one change to T005/T006 rather than three independent tasks.
