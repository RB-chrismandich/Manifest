---

description: "Task list for pilotfish-style cost-tiered model orchestration"
---

# Tasks: Pilotfish-Style Cost-Tiered Model Orchestration

**Input**: Design documents from `/specs/481-pilotfish-orchestration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the plan's Testing section and constitution Principle VI (Verify gate)
require bats coverage for the deploy/toggle behavior plus a critical-path smoke test for the
enable→deploy→disable workflow. The contract invariant files
(`contracts/{agent-frontmatter,delegation-policy,toggle-deploy}.md`) are the source of the test
assertions.

**Organization**: Tasks are grouped by user story so each is independently implementable and
testable. This is a config-only feature — paths are `configs/claude/`, `bootstrap/lib/`,
`tests/bats/`, `docs/` (no `src/` tree).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)
- Exact file paths are included in each description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new deploy-source directory the feature adds.

- [X] T001 Create the `configs/claude/agents/` source directory (deploy source-of-truth) and confirm it is NOT excluded by `.gitignore` or `.retired skill supply/.gitignore`, per plan.md Project Structure.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The bootstrap toggle + deploy plumbing that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Add `--enable-pilotfish`/`--disable-pilotfish` argument parsing, the `ENABLE_PILOTFISH=false` and `PILOTFISH_SET=false` defaults, and the two `--help` usage lines in `bootstrap/lib/config.sh` (skillclaw opt-in pattern, research R1).
- [X] T003 Add the `pilotfish:` section (`enabled: ${ENABLE_PILOTFISH:-false}`) to the `write_services_config()` heredoc and extend the services.yml→`FILE_*` awk parser to emit `FILE_PILOTFISH=true|false`, both in `bootstrap/lib/config.sh` (contracts/toggle-deploy.md).
- [X] T004 Add `gate_pilotfish_agents "$home" "$src_agents"` (two modes: **enable** copies the six role files + the reference from source, writes the marker, and injects the pointer; **disable** does a manifest-scoped prune — removes exactly the six + marker + reference + pointer) and `check_pilotfish_collision()` (pre-rsync guard, keyed on the six `PILOTFISH_AGENT_FILES` names; itself a no-op when the toggle is off) to `bootstrap/lib/common.sh`, then wire them into `bootstrap/lib/deploy.sh`'s Claude deploy path only: add `--exclude '/agents' --exclude '/references/pilotfish-delegation.md'` to BOTH rsync commands (so a disabled/foreign home is never clobbered and the reference never lands unmanaged), the pre-rsync guard before the destructive copy, and a post-copy gate call passing `"$source_dir/agents"` at BOTH rsync paths next to `gate_graphify_skill`. NB: "BOTH rsync paths" = the merge branch and the replace branch of `deploy_configs()` — both target `$TARGET_DIR` (`~/.claude`); the other assistant homes have separate deploy functions that do NOT call the gate (FR-013 — Claude home only). `check_pilotfish_collision` is a no-op when the toggle is off (internal `ENABLE_PILOTFISH==false` early-return), so a disabled bootstrap over a user's own `scout.md` neither aborts nor clobbers.
- [X] T005 Confirm `deploy_reconcile` does not orphan-scan `~/.claude/agents/` (it lists `skills`/`config` units only), so no reconcile registration is needed and neither the deployed role files nor a coexisting user agent are ever flagged/pruned by reconcile. Ownership of the agents dir is tracked by the `.pilotfish` marker for the manifest-scoped disable prune (research R6).

**Checkpoint**: Toggle + deploy plumbing ready — user stories can begin.

---

## Phase 3: User Story 1 - Enable cost-tiered orchestration (Priority: P1) 🎯 MVP

**Goal**: `--enable-pilotfish` deploys the six role-agents + the delegation-policy reference so a
Claude Code session routes mechanical/read-only work to cheaper tiers, keeps the frontier model
for planning/decision, and gates mutating/judgment/security results behind the verifier.

**Independent Test**: Enable, confirm the six agents + reference are present and readable, and
confirm a fully-specified mechanical task is delegated to a cheaper tier while the frontier model
handles planning/decision and results pass verification.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL before implementation)

- [X] T006 [P] [US1] bats: enable deploys the six agents + `pilotfish-delegation.md` to their targets (toggle-deploy INV-1); default bootstrap (no flag) deploys nothing and writes `pilotfish.enabled: false` (INV-4); no pilotfish agent files land in the Cursor/Gemini/Codex/Antigravity homes (FR-013) — in `tests/bats/deploy_pilotfish.bats`.
- [X] T007 [P] [US1] bats: agent-frontmatter invariants — exactly six files, filename stem == `name`, `model` is a built-in alias (`haiku`/`sonnet`/`opus`) with no `claude-` raw ID, `security-executor: opus`, `scout`/`Explore: haiku`, and `verifier.md` body states the CONFIRMED/REFUTED contract (contracts/agent-frontmatter.md INV-1/2/3/4); plus enable is idempotent (INV-5) — in `tests/bats/deploy_pilotfish.bats`.
- [X] T008 [P] [US1] bats: collision-abort — with a pre-existing un-owned `~/.claude/agents/scout.md`, enable exits non-zero, the message names `scout.md`, and the pre-existing file is byte-identical afterward (FR-008, toggle-deploy INV-3) — in `tests/bats/deploy_pilotfish.bats`.
- [X] T009 [P] [US1] bats: delegation-policy + budget invariants (in `tests/bats/deploy_pilotfish.bats`) — the DEPLOYED guide gains exactly one Reference Index pointer line; a **source+pointer budget assertion in `deploy_pilotfish.bats`** (reusing context_budget's 7400 cap value) proves the deployed guide (committed source + injected pointer) stays ≤ cap — this caught a real 7547>7400 overflow, fixed by condensing the verbose ALWAYS-list and syncing `configs/gemini/GEMINI.md` (FR-009, INV-6). This is DISTINCT from `context_budget.bats`, which continues to gate only the pointer-free source (unaffected — T013). The full policy prose is NOT inlined into the committed source guide (INV-2/FR-014); the reference contains the selective-verify rule (INV-4) and the security-routing rule (INV-5).
- [~] T010 [US1] Register a critical-path smoke test for the enable→deploy→verify workflow in the smoke catalog (`smoke_test.py`, Lite tier) — Principle VI Verify gate for this shipped user-facing workflow. [DISPOSITION — deferred with corrected rationale (technical spec-review Finding 5): the smoke orchestrator DOES support non-browser `cli` steps (`smoke_orchestrator/executor.py:183`), so the earlier "browser-only" claim was wrong. It is deferred because the 22-test hermetic `deploy_pilotfish.bats` sandbox suite already covers the full critical path (enable→deploy→disable→collision→re-enable→budget) deterministically; a live `cli` smoke step would re-exercise the same gate against the **real** `~/.claude` (mutating the user's actual home) for no added signal. If a smoke entry is later wanted, add a `cli` step invoking the gate helpers against a temp HOME — not the default one.]

### Implementation for User Story 1

- [X] T011 [P] [US1] Author the six role-agent files `configs/claude/agents/{scout,Explore,mech-executor,executor,verifier,security-executor}.md` with frontmatter (`name`, `description`, `model` built-in alias, `effort`) and body per contracts/agent-frontmatter.md — `scout`/`Explore`→`haiku`/low, `mech-executor`→`sonnet`/low, `executor`/`verifier`→`opus`/medium, `security-executor`→`opus`/high; `verifier` body specifies CONFIRMED/REFUTED.
- [X] T012 [US1] Author `configs/claude/references/pilotfish-delegation.md` per contracts/delegation-policy.md — MIT attribution + vendored version (pilotfish v1.1.0, FR-011), role→built-in-alias table (with what each alias currently resolves to), delegation+escalation rules, selective-verify rule (FR-003), security-routing rule + starter cue set auth/crypto/secrets/input-validation (FR-004), and the Claude-Code-handles-availability note (FR-007).
- [X] T013 [US1] Inject the one-line Reference Index pointer into the DEPLOYED `~/.claude/CLAUDE.md` at deploy time (`inject_pilotfish_pointer`, removed again by `remove_pilotfish_pointer` on disable), leaving the committed source `configs/claude/CLAUDE.md` pointer-free so `context_budget.bats` (source-only gate) is unaffected (FR-009/FR-014) and disable leaves no broken link. **Reclaim budget headroom** for the injected pointer by condensing the verbose "ALWAYS Use Parallel Agents For" sub-bullet lists in `configs/claude/CLAUDE.md` (7397→7213 bytes) to inline lists (lossless), and apply the same condensation to `configs/gemini/GEMINI.md` to keep the sibling orchestration guides in sync (Cursor's is already condensed) — a documented trim, not a cap raise.
- [X] T014 [US1] Implement the enable path of `gate_pilotfish_agents "$home" "$src_agents"` in `bootstrap/lib/common.sh`: both `agents/` AND `references/pilotfish-delegation.md` are rsync-excluded, so the gate itself copies the six role files from `$src_agents` and the reference from `$(dirname "$src_agents")/references/pilotfish-delegation.md`, writes the `.pilotfish` ownership marker, and injects the delegation pointer; `check_pilotfish_collision` (FR-008, six-name keyed) runs pre-rsync; idempotent (cp overwrites our files, marker re-stamped, inject grep-guarded — INV-5); does NOT touch `settings.json`/`settings.local.json` (FR-016).

**Checkpoint**: US1 complete — the MVP is deployable and independently testable.

---

## Phase 4: User Story 2 - Re-tier a role in one edit (Priority: P2)

**Goal**: A maintainer changes one role's model by editing that one role file's `model:` alias
(one line, one file); a model-version change requires zero edits (built-in aliases float).

**Independent Test**: Edit one role file's `model:` alias, re-deploy, confirm only that role
resolves to the new alias while other roles and the policy text are unchanged.

### Tests for User Story 2 ⚠️

- [X] T015 [P] [US2] bats: re-tier — change one role file's `model:` alias, re-deploy, assert only that role's deployed frontmatter changed and no other role or the delegation reference changed (SC-002) — in `tests/bats/deploy_pilotfish.bats`.

### Implementation for User Story 2

- [X] T016 [US2] Document the re-tier-in-one-edit procedure (edit one `model:` alias; model-version changes need zero edits because built-in aliases float) in `configs/claude/references/pilotfish-delegation.md` and `specs/481-pilotfish-orchestration/quickstart.md`.

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 - Enable, then cleanly reverse (Priority: P3)

**Goal**: `--disable-pilotfish` removes exactly the pilotfish configuration and nothing else,
leaving the rest of the Claude home intact.

**Independent Test**: Enable, snapshot `~/.claude`, disable, confirm the tree is diff-identical to
the pre-enable snapshot.

### Tests for User Story 3 ⚠️

- [X] T017 [P] [US3] bats: clean disable — enable → snapshot `~/.claude` → disable → assert the tree is diff-identical to the pre-enable snapshot; only the six agents, the reference, and the guide pointer are removed (SC-003, toggle-deploy INV-2) — in `tests/bats/deploy_pilotfish.bats`.
- [X] T018 [P] [US3] bats: main-session model untouched — after enable, the deployed `settings.json`/`settings.local.json` `model` field is unchanged and no model-alias definition file was deployed (FR-016, toggle-deploy INV-7) — in `tests/bats/deploy_pilotfish.bats`.

### Implementation for User Story 3

- [X] T019 [US3] Implement the disable branch of `gate_pilotfish_agents()` in `bootstrap/lib/common.sh`: manifest-scoped prune — remove exactly the six role files (via `PILOTFISH_AGENT_FILES`) + the `.pilotfish` marker, `rmdir` the `agents/` dir only if empty (so a coexisting user agent survives, FR-006), remove the reference and the injected guide pointer line, touching nothing else (SC-003).

**Checkpoint**: All three user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T020 [P] Documentation: add the `--enable-pilotfish`/`--disable-pilotfish` toggle row to `README.md` and `docs/GETTING_STARTED.md`, add a pilotfish section to `docs/CONFIGURATION.md`, and surface the MIT attribution + vendored version (FR-012/FR-011). Also document (a) the relationship to the subagent-driven-development skill and `parallel_agent.py` as a distinct, complementary layer — not a replacement (FR-015), and (b) the SC-001 cost-reduction target (≥40% vs frontier-only) with a manual before/after measurement method — no new harness (research R8; SC-001 is otherwise a post-launch outcome metric, not buildable work).
- [X] T021 [P] Update `bootstrap.sh --help` / any help text that enumerates service toggles so pilotfish appears alongside graphify/skillclaw (consistency).
- [X] T022 Run the full gate suite and fix any failures: `shellcheck bootstrap/lib/*.sh`, `yamllint`, `markdownlint`, `skill_naming.bats`, `context_budget.bats`, derived-doc drift (`commands_doc_drift.bats`, `generate_cursor_rules.bats`), `bootstrap_services.bats` (committed services.yml matches the generator), and `bats tests/bats/deploy_pilotfish.bats` (FR-010, SC-004).
- [~] T023 Run the quickstart end-to-end (enable → verify → re-tier → disable) and `smoke_test.py run --tier Lite` to confirm the Verify gate passes (Principle VI); confirm enable→confirm-deployment takes under 5 minutes (SC-006); and spot-check that a security-sensitive prompt routes to `security-executor` (not the cheapest tier) per the deployed policy — the runtime half of SC-005 (its buildable half is covered by T007/T012). [DISPOSITION: deploy logic verified via the bats sandbox (22 tests green); a live ./bootstrap.sh --enable-pilotfish run mutates the real ~/.claude, so it is a user-initiated validation, not run unprompted.]

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **BLOCKS all user stories** (T004's deploy
  function is called by every story's deploy branch).
- **User Stories (Phase 3–5)**: all depend on Foundational. US1 is the MVP.
- **Polish (Phase 6)**: depends on all desired user stories.

### User Story Dependencies

- **US1 (P1)**: after Foundational. Delivers the enable/deploy path — the MVP.
- **US2 (P2)**: after US1 (needs the deployed agent files to re-tier). Small: one test + docs.
- **US3 (P3)**: after US1 (the disable branch removes what US1's enable branch deployed). US3's
  `gate_pilotfish_agents()` disable branch is the counterpart to US1's enable branch (T014),
  so it edits the same function — do US3 after US1, not in parallel with it.

### Within Each User Story

- Tests first (write, watch fail), then implementation.
- Agent files + reference (T011/T012) before the enable branch that copies them (T014).
- The guide pointer (T013) before the budget assertion in T009 can pass.

### Parallel Opportunities

- Foundational T002/T003 touch the same file (`config.sh`) → **not** parallel; T004/T005 touch
  `deploy.sh` → sequential with each other.
- US1 tests T006–T009 are all in the same bats file but assert independent behaviors — author
  together, but they share one file so treat edits as sequential blocks ([P] marks logical
  independence, not concurrent writes to one file).
- T011 (six agent files) is genuinely parallel across the six files.
- Docs T020/T021 touch different files → parallel.

---

## Parallel Example: User Story 1

```bash
# The six role-agent files are independent (different files) — author in parallel:
Task: "Author configs/claude/agents/scout.md (model: haiku, low)"
Task: "Author configs/claude/agents/Explore.md (model: haiku, low)"
Task: "Author configs/claude/agents/mech-executor.md (model: sonnet, low)"
Task: "Author configs/claude/agents/executor.md (model: opus, medium)"
Task: "Author configs/claude/agents/verifier.md (model: opus, medium; CONFIRMED/REFUTED)"
Task: "Author configs/claude/agents/security-executor.md (model: opus, high)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → Phase 2 Foundational (toggle + deploy plumbing).
2. Phase 3 US1 → **STOP and VALIDATE**: enable, confirm the six agents + reference deploy, run
   the smoke test. This is a shippable MVP.

### Incremental Delivery

1. Setup + Foundational → plumbing ready.
2. US1 → the enable/deploy MVP (demo cost-tiered delegation).
3. US2 → prove one-line re-tiering.
4. US3 → prove clean reversal + settings safety.
5. Polish → docs + full gate + smoke.

---

## Notes

- [P] = logically independent; where tasks share one file (`config.sh`, `deploy.sh`, the single
  bats file) apply edits as sequential blocks even when [P]-labeled.
- Config-only: no runtime code, no `settings.json` change (FR-016); roles use built-in Claude
  Code model aliases that float to current versions.
- Security-routing (FR-004) is a guardrail — never weaken it in later edits.
- Commit after each task or logical group (when the user asks).
- The `after_implement` hook runs `speckit-audit-tasks` — the Verify gate audits genuine task
  completion before commit.
