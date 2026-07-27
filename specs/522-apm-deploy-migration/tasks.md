---
description: "Task list for APM-Based Deploy Pipeline (Drift Elimination)"
---

# Tasks: APM-Based Deploy Pipeline (Drift Elimination)

**Input**: Design documents from `specs/522-apm-deploy-migration/`

**Prerequisites**: spec.md, plan.md (required); `decision-record.md` is produced by Phase 0 and **gates every task after T006**

**Revision**: v4, after five adversarial reviews, the `/speckit-analyze` pass (v3, which added T048–T053), and a technical `spec-review` pass. The sequencing change that matters most is still v2's: **legacy writers are gated off a domain before that domain's first APM deploy** (was three phases later, which created a guaranteed clobber). v3 applies the same principle in three more places — the spike now measures every assumption the GO decision rests on (T005 cells d/i/ii), the replacement contributor loop lands before the writer it replaces (T055 before T014/T015), and binary integrity is *implemented* rather than only recorded and tested (T054).

**Tests**: INCLUDED and load-bearing. The feature's value is four filesystem properties. FR-023 requires each to have an automated test that fails against the pre-migration pipeline **and asserts its precondition before its postcondition** — an idempotence diff on an empty tree, or an orphan check whose "before" state was never established, passes vacuously while proving nothing. FR-022/FR-035a require isolation to be *asserted*, not assumed.

**Organization**: Grouped by phase and user story. **Phase 0 is a hard gate**: NO-GO terminates the feature with zero Manifest source modified (FR-001), which is a *successful* outcome.

## Format: `[ID] [P?] [Story] Description → [FR refs]`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1/US2/US3/US4 (spike/prereq/polish carry no story label)

---

## Phase 0: Feasibility Spike (BLOCKING GATE) 🚦

**Purpose**: Settle whether the published-package path deploys file primitives at user-global scope, with a rig whose results can be trusted.

**⚠️ CRITICAL**: T001–T006 MUST NOT modify anything under `configs/`, `bootstrap*`, `.skillshare/`, or `tests/`. All work in a scratch directory and an isolated `HOME`.

- [x] T001 [P] Install the **pinned** `apm` CLI at **v0.26.0**; record the exact resolved version, install method, and the **checksum/signature of the downloaded binary** — the tool writes hooks and MCP definitions into five home trees, so its own install channel is part of the trust surface, not a footnote. → FR-029, E8
- [x] T002 [P] Stand up the disposable environment: throwaway `HOME`, throwaway git repo, scratch dir, using `test-isolate-ambient`'s isolation handles. *(The v2 warning not to cite that skill is obsolete: merging `origin/main` on 2026-07-25 committed it to `.skillshare/skills/`, so a fresh clone and CI can now follow this task. Confirm it is still present before relying on it — that is one `ls`, and the whole reason the warning existed.)* → FR-022, R7
- [x] T003 **Sentinel check — run before trusting any spike result.** Hash the real `~/.claude` tree, run a sandboxed `apm install --global`, re-hash, and assert **byte-identical**. If `apm` resolves the OS home via a syscall that ignores `$HOME`, every "isolated" result from here on is silently invalid while reporting clean. This is the single assumption the entire GO/NO-GO rests on. → FR-035a, SC-007
### Publish gates — MUST exist before anything is published 🔒

*Moved here from Phase 7 by the analyze pass. Publication is irreversible; a scan or provenance check that arrives after the first publish protects nothing, and Constitution VII.1/VII.4 are MUSTs. These three tasks block T004.*

- [ ] T048 Implement the **blocking pre-publish content scan**: secrets, credentials, machine-local paths, private material. It must **fail the publish**, not warn. Wire it so that no publish path — including the throwaway spike package — can run without it. → FR-030, Constitution VII.4
- [ ] T049 Implement the **provenance gate**: publish only from a clean working tree at a tagged commit, blocking otherwise. → FR-038, Constitution VII.1
- [ ] T050 Enable **package integrity verification on install** (hash or signature, fail-closed) from the very first install, and open the threat-control section of `decision-record.md` covering typosquatting, dependency confusion, and registry-account compromise, each naming its enforcing mechanism. *(Split out of T042, which was Phase 7 — installs begin in this phase.)* → FR-018

- [~] T004 [P] Author a **throwaway package** in the scratch dir: two skills, one agent, one hook. Publish it to whatever registry the published model will use — cell (b) of T005 requires a real publish, and provisioning that access is the schedule risk behind SC-009's two-day box. **Blocked by T048–T050**: this is a real publish to a real registry and is gated exactly like a release. → FR-002, FR-030, SC-011
- [x] T005 Run the **deployment matrix** and record raw output per cell: (a) locally-cloned source at `--global`; (b) **published package installed by name** at `--global` — the decided model; (c) `--target claude,cursor,antigravity` explicitly; (d) **publish-free local link/dev loop** — install or link a local package directory *without* publishing, edit a source file, and confirm the edit propagates with no registry round-trip. Report results **per primitive type** (skill / agent / hook) — an aggregate "file primitives deploy" can mask hooks failing while skills succeed, since hooks live inside `settings.json` rather than as standalone files. On the deploying cell, also measure: rename→stale-file cleanup; hand-edit→retention **and whether the warning appears at install time or only under a separate `apm audit`** (E1 is open on exactly this); re-install→byte-identical. Two further measurements, both previously deferred past the gate although the migration cannot survive either answering wrong: **(i) symlinked targets** — replicate the real fan-out (`~/.cursor/skills` → `~/.claude/skills`) inside the throwaway `HOME` and record whether `apm install` follows, replaces, deletes, or errors on the symlink; **(ii) installer-written mutation** — after an install, mutate a deployed file the way `install_issue_hooks.sh` mutates the deployed `command_config.yml`, re-install, and record whether the tool can express "my own installer wrote this" or treats it identically to a human hand-edit. → FR-002, FR-032, FR-033, FR-034, E1
- [x] T006 Write `decision-record.md`: **GO or NO-GO**, per-primitive-type results, raw evidence, exact version, and the confirmed surfacing mechanism for retained edits. Include a **known-good control case** the rig demonstrably detects, so operator error cannot masquerade as NO-GO. Record an explicit GO/NO-GO input for each of T005's three assumption cells — publish-free loop (d/FR-032), symlink fan-out (i/FR-033), installer-vs-human mutation (ii/FR-034). Each is a structural blocker that invalidates a downstream task if it answers wrong (T055, T013, T051 respectively), so **"not measured" is a NO-GO for that cell, not a deferral** — the point of a blocking gate is that nothing load-bearing crosses it unverified. → FR-003, FR-032, FR-033, FR-034, FR-035b, SC-009. **NO-GO ends the feature — report it plainly and stop; the homegrown hash-manifest deployer is the documented fallback to evaluate next.**

**Checkpoint 🚦**: Nothing below starts until `decision-record.md` records GO.

---

## Phase 1: Prerequisites

**Purpose**: Clear structural blockers and build the safety instruments **before** the coexistence window opens.

- [ ] T007 Wire a flag/environment override through to the existing `config_path` parameter in `configs/claude/scripts/agents/config.py` (note: **not** `configs/claude/scripts/config.py`, which does not exist; the constructors already accept the parameter, so this is wiring, not new capability). Add a test covering both resolution modes. → FR-020, R5
- [ ] T008 Build the isolated-`HOME` deploy harness in `tests/bats/`, and `tests/bats/apm_isolation_sentinel.bats` that runs the T003 sentinel assertion **on every deploy-test run**, not once. → FR-022, FR-035a, SC-007
- [ ] T009 Write `tests/bats/apm_ownership_boundary.bats` and run it against the **current** pipeline to capture the baseline. Enumerate every path each deployer writes, and **validate the enumeration itself** against a `find` over a real deployed tree — an incomplete enumeration passes forever while seeing nothing. → FR-014
- [ ] T010 Build the **ownership diagnostic** into `env-check`/`config-audit` now, reporting which pipeline owns each area and flagging any area claimed by both. Review moved this *before* the coexistence window: a diagnostic delivered afterwards polices a window that has already closed. → FR-015, SC-006
- [ ] T011 Add a **per-domain selector** to the legacy deploy path (`deploy_configs()` is monolithic today, R6) so unmigrated domains can be redeployed without touching migrated ones. This is the mechanism FR-019's rollback depends on; without it, "re-run bootstrap for unmigrated domains" is not an available action. → FR-019, R6
- [ ] T012 [P] Write `migration-inventory.md`: classify every deployed artifact as markdown primitive / script / config YAML / generated. **Decide explicitly** what happens to the 54 top-level (88 recursive) scripts and the config YAMLs — a deferral leaves the drift fix partial by definition and must be stated as such. Include the `command_config.yml` case: it is mutated by `install_issue_hooks.sh` in the *deployed* copy, so scripted mutation must be distinguishable from a human edit or the first opt-in freezes the file permanently under retention. → FR-020, FR-034, R3
- [x] T013 **Decided by FR-021a (amended 2026-07-27) — this task now implements, it no longer chooses.** `.apm/skills` is the sole physical source of truth; `.skillshare/` is removed (see T056–T059). The symlink fan-out question FR-033 posed is **measured, not assumed**: T005 cell (i) recorded that apm *preserves* a symlinked target directory rather than replacing it with an independent copy, so `~/.cursor/skills -> ~/.claude/skills` survives an APM deploy and no per-harness divergence is introduced. Document that result against FR-033's four criteria and record the disk/build cost as N=1 (single tree, fan-out by symlink). → FR-021a, FR-033, R2
- [ ] T051 Implement the mechanism that distinguishes **installer-written mutation from a human edit**, so retention does not permanently freeze a file that Manifest's own scripts modify (`install_issue_hooks.sh` → deployed `command_config.yml`). T012 only records the case; this builds the answer, and it must land **before** any config YAML migrates. **Built on T005(ii)**: if the spike showed the tool cannot distinguish the two, this task is the wrapper that supplies the distinction externally (e.g. re-running the installer through the package rather than against the deployed copy) — say which, rather than discovering the constraint here. → FR-034, R3
- [ ] T054 Implement `apm` **binary acquisition and integrity verification in `bootstrap.sh`**: download the pinned v0.26.0 artifact, verify it against the checksum/signature recorded by T001, and **fail closed** — no fallback to an unverified binary, no "warn and continue". T001 records the value and T042 asserts the gate fails closed; without this task neither has a subject, and the binary that writes hooks and MCP entries into five home trees arrives unverified. Distinct from T050, which verifies *packages* at install time — this verifies the tool doing the installing. → FR-029, E8

**Checkpoint**: Blockers cleared, instruments built, baseline captured.

---

## Phase 2: Gate the legacy writers (BLOCKER fix)

**Purpose**: The MVP domain (`~/.claude/skills`) currently has **two** live writers — `deploy_home_skills()` on every `./bootstrap.sh`, and `sync-skills.sh` in `~/.local/bin`, the documented daily skill-dev workflow. Shipping an APM-managed domain before gating them guarantees an ordinary contributor action clobbers APM-owned files under a different ownership model. **Gating a writer is only half the job** — T055 lands the replacement daily workflow first, so this phase removes a path instead of removing the *only* path.

- [ ] T055 **Land the publish-free local development loop before removing the writer it replaces** (per T005 cell (d)): a contributor edits a skill under `.apm/skills/` (post-FR-021a; `.skillshare/skills/` no longer exists) and sees it in their own `HOME` without publishing to a registry. This was T044 in Phase 7 — five phases *after* T015 gates `sync-skills.sh`, which left every contributor (including whoever is implementing Phases 3–6) with a registry publish as the only way to test a one-line skill edit. FR-021 requires the existing lifecycle workflow keep functioning; FR-027 removes its writer; this task is what makes both true at once. Document the new loop in the same change that gates the old one. → FR-032, FR-021, FR-027
- [ ] T014 Gate `deploy_home_skills()` (`bootstrap/lib/common.sh`, called from `deploy_configs()`) per-domain: skip any domain `.apm/` owns, continue deploying the rest. → FR-027, FR-014
- [ ] T015 Gate `sync-skills.sh` the same way, including the copy installed at `~/.local/bin/sync-skills` — and make it **say** it skipped a domain rather than silently no-op, or contributors will read the silence as success. The skip message must **name T055's replacement command**: a contributor told only that their daily tool declined to do anything has been handed a dead end. → FR-027, FR-021
- [ ] T016 Re-run `apm_ownership_boundary.bats` and confirm the MVP domain has **zero** writers pending APM's arrival (not two, not one-plus-a-stale-CLI). → FR-014, FR-027
- [ ] T053 Write and **test** the **un-gate procedure** that returns a gated-but-not-yet-migrated domain to the legacy writer. This phase deliberately leaves the domain with no writer at all; if the first APM deploy stalls (failed publish, rejected package, late NO-GO), that domain is un-updatable by any mechanism until someone intervenes. The procedure must work mid-migration, not only as part of the full rollback. **It must also reclaim the files APM already wrote**: the legacy writer overwrites the paths *it* knows about, so anything APM added that the legacy pipeline never writes survives as an orphan owned by neither pipeline — the exact untracked-hybrid state this feature exists to eliminate. Specify and test the reclamation step (`apm uninstall` for the domain, or a scripted purge driven by the lockfile's file list), then assert with `apm_ownership_boundary.bats` that the domain has exactly one owner afterwards. → FR-039, FR-019, FR-014

**Checkpoint**: The domain is unowned and safe to hand over, **and the window is escapable**. Only now may an APM deploy touch it.

---

## Phase 3: User Story 1 - Reproducible, self-cleaning deployment (P1) 🎯 MVP

**Goal**: All four drift properties on **one domain, one harness**, legacy pipeline still owning everything else.

**Independent Test**: `bats tests/bats/apm_deploy_isolated.bats` green, with every precondition asserted.

### Tests first

- [ ] T017 [US1] Write `tests/bats/apm_deploy_isolated.bats` — **before** the migration, and demonstrate each test fails against the current pipeline. Every case asserts its precondition first: reproduce-from-package-and-lockfile, then diff against an **expected file manifest** (a non-empty tree assertion, so an install that silently no-ops cannot produce an empty-vs-empty pass); assert old-file **present** → rename → re-deploy → assert old-file **absent** and new-file present (so a rename that never took hold cannot look like successful cleanup); hand-edit → retained **and surfaced in the deploy workflow output**; re-deploy → byte-identical. Include a corrupted-lockfile case that must fail loudly, not deploy partially. **Enumerate the named historical drift instances in the test file** — the `mcpServers` clobber, the `__pycache__` orphan, the unpruned `~/.cursor/rules`, the toggle-off skill copy, the stale `COMMANDS.md` — as comments on the cases that generalize them, so SC-008's "each class has a regression test" is traceable to the specific bugs it claims to have killed rather than asserted at the class level. → FR-004..FR-007, FR-023, SC-001..SC-004, SC-008

### Implementation

- [ ] T018 [US1] Author `apm.yml` (pinned tool version, explicit targets) and `.apm/` for **one** domain, per T013's arrangement; publish it; commit `apm.lock.yaml`. → FR-007, FR-017
- [ ] T019 [US1] Run T017 to green, iterating the package. Record actual command output — a plausible-looking config is not evidence. → FR-004..FR-007
- [ ] T052 [US1] **Conditional on T005's finding**: if retention is silent at install and surfaced only by a separate `apm audit`, wire that audit into the deploy path so retention is never silent, and confirm retained files also appear in the drift report. If T005 shows install-time surfacing already satisfies both channels, close this task with that evidence recorded — do not close it unexamined. → FR-005, FR-008
- [ ] T020 [US1] Re-run `apm_ownership_boundary.bats` **at this exact point** — the first moment two pipelines are simultaneously live is the highest-risk instant for a double write, and v1 only checked at deletion points. → FR-014
- [ ] T021 [US1] Verify drift detection: compare `apm audit` against `deploy_reconcile.sh` on a deliberately-drifted tree and document any class the new tool misses **before** relying on it. → FR-008
- [ ] T022 [US1] Add `tests/bats/apm_supply_chain.bats` — an **independent** tree hash computed by something `apm` does not control, wired as a standing gate. The lockfile is generated by `apm` and `apm audit` reads it back; alone they are one party checking its own work. → FR-036, E9
- [ ] T023 [US1] Register the deploy suite as this feature's **Verify-gate smoke coverage**: missing coverage is never a pass. → Constitution VI (gate-mapped, not FR-mapped)

**Checkpoint**: The thesis is proven or disproven on real Manifest content.

---

## Phase 4: User Story 2 - One source builds every harness (P2)

- [ ] T024 [US2] Extend `apm.yml` to all five harnesses, **naming `antigravity` explicitly** (excluded from the `all` meta-target, E2), and assert every supported harness appears in the resolved target list. → FR-011
- [ ] T025 [US2] Build the **equivalence harness** for the three per-harness generators. "Two independent clean runs" means **fresh scratch dir, fresh clone, no shared build cache** — name the nondeterminism being controlled for, or a second run from the same cache proves nothing. Enumerate intentional differences in writing. → FR-010
- [ ] T026 [US2] **Functional consumption check**: deploy the new build's output into an isolated `HOME` and confirm a real harness actually loads it. Content-equal is not behavior-equal, and a static diff alone should not license deleting the only working pipeline. → FR-010
- [ ] T027 [US2] Run the **full CI mirror now**, before any deletion — `shellcheck`, `yamllint`, `bats tests/bats/`, `pytest tests/python/`, and the changed-file gate with `--from-ref origin/main`. Review moved this ahead of the irreversible step; a repo-wide change drags never-gated files into the changed-file gate, and discovering that after deletion is the wrong order. → SC-005
- [ ] T028 [US2] Delete **exactly four** scripts, each only after its equivalence (T025) and functional check (T026) pass: `generate_cursor_rules.sh`, `generate_cursor_agents.py`, `generate_cursor_mcp.py`, and `deploy_reconcile.sh` (after T021). Delete, do not stub. Re-run the ownership test after each. → SC-005, FR-014
- [ ] T029 [US2] **Retain** `generate_commands_doc.py` and document why: it renders `docs/COMMANDS.md` and injects an index into `GEMINI.md`/`AGENTS.md`, and the build tool's target matrix generates no catalog/documentation indexes. State this in the docs rather than leaving an apparent omission. **Conditional check, cheap and skippable**: the generator resolves its catalog from `_REPO_ROOT / .skillshare/skills` (overridable via `COMMAND_CATALOG_SKILLS_DIR`), i.e. the *repo* source of truth, not a deployed home — so the migration alone does not touch it. If, and only if, T013's `.apm/skills` ↔ `.skillshare/skills` resolution changes the repo-side path, update that default and its `--check` fixtures in the same change. → FR-037, E10
- [ ] T030 [US2] Remove the **109** committed `.mdc` artifacts from version control and update hygiene gates that assume their presence — including the end-of-file-fixer/double-newline interaction and any count-based doc assertions. → FR-012
- [ ] T031 [US2] Confirm one source edit propagates to all five harness outputs in a single build, and that `bats tests/bats/` + `pytest tests/python/` pass with the four generators gone. → FR-009

---

## Phase 5: User Story 3 - `bootstrap.sh` narrows (P3)

- [ ] T032 [US3] Remove configuration-content deployment for migrated domains from `bootstrap/lib/deploy.sh`, leaving CLI installation, auth, MCP config, toggles, and the settings merge untouched. Re-run the ownership test. → FR-013, SC-006
- [ ] T033 [US3] Verify service-toggle behavior: a disabled component must be **absent** from the home tree after deploy. Assert absence, not merely that a copy step wasn't invoked. → FR-016
- [ ] T034 [US3] Prove the rollback using T011's selective deploy **and T053's reclamation step**: take a partially migrated machine, follow the procedure, confirm a working configuration with no legacy-owned files stripped **and no APM-written orphans left behind** — diff the rolled-back tree against a never-migrated one and account for every difference. A rollback that returns the writer but not the file ownership has not rolled back. → FR-019, FR-014
- [ ] T035 [US3] Verify the constitution amendment (v2.0.0) is consistent with the shipped state, and update the guidance that still names `./bootstrap.sh --reconfigure` as the drift-correction command (`CLAUDE.md`, `configs/claude/CLAUDE.md`, `docs/CONFIGURATION.md`, `docs/GETTING_STARTED.md`). → Constitution I/V

---

## Phase 6: User Story 4 - Compartmentalized `manifest-` plugins (P4, OPTIONAL)

**⚠️ Droppable.** US1–US3 deliver the complete drift fix. Do not let US4 block the merge.

**⚠️ The v1 ten-domain split is invalidated** — `a11y-audit` and `config-audit` each match two proposed domains, `pr-smoke` lands semantically wrong, ~25 of 107 skills match none, and `git_ops.sh` couples 12 skills across four domains. Treat the ten names as vocabulary, not design.

- [ ] T036 [US4] Derive the **authoritative** skill→domain map by **functional analysis of all 107 skills**, not name-prefix matching. Assert the partition: every skill in exactly one domain, none in two, none in zero. → FR-025, SC-010
- [ ] T037 [US4] Map the **shared-script dependency graph** (`git_ops.sh` → 12 skills across four domains; `git_platform.sh` → two) and decide: place shared components so partial enablement still functions, or declare cross-plugin dependencies explicitly. If shared scripts stay global regardless of enablement, say so — that makes compartmentalization cosmetic for functionality and real only for catalog loading, and the docs must not overclaim. → FR-028
- [ ] T038 [US4] Generate the plugins via `apm pack` with `manifest-` applied to **both** the plugin manifest name and the marketplace entry name. Note the evidence limit: marketplace name governs `enabledPlugins` and `/plugin` display, while component namespacing is documented as driven by `plugin.json`'s `name` — prefixing both is belt-and-braces, not a proven equivalence. → FR-026, E6
- [ ] T039 [P] [US4] Write `tests/bats/manifest_plugin_naming.bats`: prefix present in both locations; skill→plugin mapping is a true partition; enabling one plugin loads only that domain **and that domain still functions with siblings disabled** (the FR-028 case — a load-only test would pass while the feature is broken). → FR-025, FR-026, FR-028, SC-010
- [ ] T040 [US4] Verify install-by-name on a machine with no Manifest clone, into an isolated `HOME`. Document honestly what a plugin cannot carry: permissions and env settings do not travel this way. → FR-024, E6

---

## Phase 7: Polish & Cross-Cutting

- [ ] T041 [P] Update documentation: what each pipeline owns, deploy, drift detection and correction, rollback, the pinned version and its upgrade procedure, and the retained `generate_commands_doc.py`. Retire references to deleted generators. → FR-037
- [ ] T042 Complete the **supply-chain gates** begun in Phase 0: add `tests/bats/apm_supply_chain.bats` asserting that package integrity verification (T050), **binary integrity verification in `bootstrap.sh` (T054)**, the pre-publish scan (T048), and the provenance gate (T049) each **fail closed** when their subject is invalid, and wire `apm audit` into CI. *(The gates themselves moved to Phase 0 — this task makes them regression-proof, since FR-018 was the one cross-cutting invariant with no enforcing test.)* → FR-018, FR-029
- [ ] T043 Verify **SC-011** across the whole project history: every publish performed — spike and release alike — has a preceding gate record for T048 and T049. A publish with no gate record is a failure regardless of whether anything leaked. → FR-030, FR-038, SC-011
- [ ] T044 [P] Implement and document the **offline install path** (pinned local artifact, no registry access). *(The publish-free local development loop moved to **T055** in Phase 2 — it had to precede the gating that removes the workflow it replaces, not trail it by five phases. Verify here that the two paths coexist: an offline install must not clobber a linked local package, and vice versa.)* → FR-031, FR-032
- [ ] T045 Add the **upgrade gate**: bumping the pinned tool version must re-run equivalence and idempotence checks and fail if they are not run. Documentation alone does not satisfy the requirement. → FR-017
- [ ] T046 Verify FR-001 held: diff `configs/`, `bootstrap*`, `.skillshare/`, `tests/` against the pre-spike tree and confirm Phase 0 modified nothing **except** the publish gates T048–T050, which are new files and are the one sanctioned exception (they had to exist before the spike could publish). An instruction is not a check. → FR-001
- [ ] T047 Validate every Success Criterion SC-001…SC-011 with the named evidence command per criterion, and update the CLAUDE.md active-feature block. → SC-001..SC-011 (rollup)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 0 (Spike)**: no dependencies, except that **T048–T050 block T004** — nothing is published before the gates exist. **Hard gate**; NO-GO terminates.
- **Phase 1 (Prereq)**: after GO. T012/T013 are [P]; T051 must precede any config-YAML migration; **T054 must precede any machine installing `apm` via `bootstrap.sh`** — the binary is verified before it is trusted, not after.
- **Phase 2 (Gating)**: after T013 (needs the domain arrangement decided). **Blocks Phase 3 absolutely.** **T055 precedes T014/T015** — the replacement contributor loop lands before the writers it replaces are gated. T053 must land in this phase, not after it — it is the escape hatch for the window this phase opens, and it reclaims APM-written files rather than only restoring the legacy writer.
- **Phase 3 (US1)**: after Phase 2. Deploying before gating is the BLOCKER this ordering exists to prevent. T052 is conditional on T005's measurement.
- **Phase 4 (US2)**: after US1.
- **Phase 5 (US3)**: after US2 and T011 (rollback needs the selective deploy).
- **Phase 6 (US4)**: after US2. Independent of US3; droppable.
- **Phase 7 (Polish)**: now genuinely polish — the publish gates moved to Phase 0, leaving T042 (regression-proofing them) and T043 (verifying SC-011 across history). T046/T047 last.

### Task ID note

IDs T048–T053 were added by the analyze pass, and **T054–T055 by the technical spec-review pass**; all are placed in the phases where they execute, not in numeric order. **A task ID is a stable identifier, not a position.** Read execution order from the phase headings and this section.

### Critical Path

T048 → T049 → T050 → T004 → T005 → T006 (GO) → T013 → T054 → T055 → T014 → T053 → T016 → T017 → T019 → T025 → T026 → T027 → T028 → T032 → T047

Changes from v2: the **publish gates now head the critical path** (the spike cannot publish without them); **T053** (un-gate + reclamation) is on it because Phase 2's zero-writer window must be escapable before US1 is allowed to stall in it; and the review pass added **T054** (binary integrity in `bootstrap.sh`, which gates the first real install) and **T055** (publish-free loop, which gates the writer removal). T003's sentinel remains a hard precondition for trusting anything T005 reports, and T005 now carries the three assumption cells the GO decision depends on.

### Parallel Opportunities

- T001 ‖ T002 ‖ T004 (spike setup); T012 ‖ T013 (inventory + arrangement)
- T039 authoring ‖ T036 map derivation; T041 ‖ T044
- **US4 can proceed in parallel with US3** — it needs only the US2 build

---

## Implementation Strategy

### Spike first, commit nothing

1. Phase 0 alone, two working days, zero Manifest source touched.
2. **Validate the rig before the result** (T003 sentinel, T006 control case). An unvalidated rig turns both GO and NO-GO into coin flips.
3. **STOP and DECIDE.** NO-GO → report, keep the record, evaluate the homegrown hash-manifest deployer instead.

### Gate before you deploy

Phase 2 exists because the MVP domain has two live writers today. Handing a domain to APM while `sync-skills` still writes it is not a race condition to monitor — it is a guaranteed clobber on the next ordinary contributor action.

### MVP (US1)

Four drift properties green in an isolated `HOME`, against real content, each with its precondition asserted, legacy pipeline untouched elsewhere.

### Incremental delivery

1. MVP (US1) → 2. US2 (all harnesses; four scripts and 109 artifacts deleted) → 3. US3 (bootstrap narrowed, rollback proven) → 4. US4 *(optional)* → 5. Polish.

### Notes

- **The gate is real.** T006 NO-GO is a legitimate terminal state; do not soften it into "proceed with caveats."
- **Two irreversible acts**: deleting a generator, and **publishing**. The second is new under the published model and is why T043's scan blocks rather than warns.
- **Isolated `HOME` or it did not happen**, and isolation itself is asserted (T003/T008) rather than assumed.
- **Write the failing test first** (T017). A test authored afterwards cannot demonstrate it caught anything.
- **Assert preconditions.** Empty-vs-empty diffs and unasserted rename "before" states are the two vacuous passes most likely here.
- Editing skill files triggers the cursor-rules and guide generators until T028 removes them — regenerate and run the full pre-commit chain before any PR during Phases 1–4.
- **New scripts inherit the `--help` gate.** As of `origin/main` (merged 2026-07-25), every user-facing entry point — `.sh` **and** `.py` — must handle `--help` (usage + flags, ≤15 lines, exit 0, **before any config/state lookup**), and coverage is *enumerated*, not listed, by `tests/bats/help_coverage.bats`. The scripts this feature adds (T011's selective deploy, T048's scan, T049's provenance gate, T050's integrity check, T054's binary verification, T055's local-loop entry point) are all in scope automatically; opt out only with `# help-coverage: exempt — <why>` under the shebang. Run that suite as part of T027, not as a surprise at PR time.
- Constitution II requires parallel-agent cross-verification before merge. Judge on completed agents plus substantive findings: in this feature's own review round, two of four panel agents failed on environment errors and collapsed consensus to 0.00 — a false BLOCKED.
- Commit after each task or logical group.

---

## Phase 8: Deprecate skillshare completely (FR-021a) 🗑️

*Added 2026-07-27 by maintainer decision. This inverts a former non-goal — see
the amendment note in `spec.md` Non-Goals and FR-021a.*

**NOT gated by the Phase 0 checkpoint** (corrected 2026-07-27). That checkpoint
exists to stop a working pipeline being deleted before its replacement is
proven, and it asks whether the **published-package** path deploys primitives.
Phase 8 asks a different question — which repo directory is the skills source of
truth, and does skillshare tooling exist — and introduces no APM runtime
dependency: deployment still runs through `bootstrap.sh`'s `deploy_home_skills`.
The original blanket gating note was over-cautious.

**Invariant (FR-021a)**: no commit that ships may leave two authoritative skill
trees. Each task below moves consumers *before* the tree, so the repo is never
in a state where the catalog resolves to nothing.

- [x] T056 **Inventory every consumer of `.skillshare/`** and record it as a
  checklist in the same doc T013 writes — do not rely on a grep at implementation
  time. Known at authoring: `configs/claude/skills` (compat symlink),
  `command_catalog.py` (`COMMAND_CATALOG_SKILLS_DIR` default),
  `generate_commands_doc.py`, `deploy_home_skills` in `bootstrap/lib/deploy.sh`,
  `tests/bats/subagent_policy.bats`, `tests/bats/skill_naming.bats`,
  `.skillshare/config.yaml`, `.skillshare/.gitignore`, `sync-skills.sh`, and the
  SkillClaw `/skill-evolve` PR target. Re-derive the list with
  `grep -rn skillshare` and treat any consumer not on it as a finding.
  **Measured 2026-07-27**: 151 non-spec files reference `skillshare`
  (plus 5 inside `.skillshare/skills` itself, and the historical spec
  records, which are dated artifacts and MUST NOT be rewritten). The
  authoring-time list above is therefore a starting point, not the inventory —
  the blast radius is roughly an order of magnitude larger, and includes
  user-facing docs (`README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`)
  and `bootstrap/lib/common.sh`. → FR-021a
- [x] T057 **Repoint every consumer to `.apm/skills` in one change**, keeping the
  tree in place. The suite must be green with `.skillshare/` still on disk but
  nothing reading it — that is the proof the move is safe, and it is the only
  point where a rollback is free. → FR-021a
- [x] T058 **Move the skills and delete `.skillshare/`.** `git mv` so history
  follows. Remove `.skillshare/config.yaml`, `.skillshare/.gitignore`, and the
  `configs/claude/skills` compat symlink. Verify the deployed home still
  resolves: `~/.claude/skills` populated and the four harness symlinks intact.
  → FR-021a, FR-033
- [x] T059 **Retire the skillshare tooling and its documentation.** `sync-skills.sh`
  and any `skillshare install|audit|check|update` guidance in `CLAUDE.md`,
  `.claude/CLAUDE.md`, `docs/`, and SkillClaw's `/skill-evolve` target. A skill
  that still tells a contributor to run `skillshare` after the tree is gone is a
  broken instruction, not a stale doc. → FR-021a, FR-027
