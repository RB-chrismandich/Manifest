---
description: "Task list for emdash Support (Full Config Inheritance)"
---

# Tasks: emdash Support (Full Config Inheritance)

**Input**: Design documents from `specs/483-emdash-support/`

**Prerequisites**: plan.md, spec.md (required); research.md, data-model.md, contracts/, quickstart.md (available)

**Tests**: INCLUDED — the spec mandates a hybrid verification (FR-011: automated launch-env simulation + manual smoke), and this is a lifecycle-gated feature, so the automated inheritance test is the Verify-gate smoke for the user-facing workflow (run Manifest via emdash).

**Organization**: Grouped by user story (US1 = MVP). emdash is an **external harness** — no `~/.emdash/`/`configs/emdash/` deploy tree (FR-008); tasks are a shared probe + a committed `.emdash.json` + tooling/docs. No `bootstrap/lib/deploy.sh`, services.yml, or `agents/*.py` provider changes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1/US2/US3 (setup/foundational/polish carry no story label)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test fixtures shared by the automated verification.

- [x] T001 [P] Create the launch-env test-fixture skeleton under `tests/bats/fixtures/emdash/` reproducing data-model E3, faithful to the repo's REAL layout (hooks HOME-side, permissions in the tracked repo file — spec-review F3): `home/.claude/{skills/<one>/SKILL.md, agents/<one>.md, settings.json (Manifest **hooks** + mcpServers)}`; `worktree/{CLAUDE.md, AGENTS.md, .claude/agents/<one>.md (repo-side subagent for D2), .claude/settings.local.json (**permissions only**, no hooks)}`; and TWO emdash-merged variants — `home/.claude/settings.json.emdash-merged` (emdash `Stop` hook `curl http://127.0.0.1:$EMDASH_HOOK_PORT/hook` + `EMDASH_MARKER` appended alongside the pre-existing Manifest **hooks**, for the preservation assertion) and `worktree/.claude/settings.local.json.emdash-merged` (emdash hook appended alongside the repo **permissions**, for the not-corrupted assertion) — plus a `README.md` documenting the layout. [C4][F3]

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared inheritance probe underpinning both US1 (automated + manual verification) and US3 (live `/env-check`).

**⚠️ CRITICAL**: T002 blocks US1 and US3 (US2 is independent of it).

- [x] T002 Implement the inheritance probe `configs/claude/scripts/emdash_inherit_check.sh` per `contracts/inheritance-probe.md`: flags `--home`/`--worktree`/`--json`/`--help`; dimensions D1–D6 (skills, subagents, hooks, MCP, orchestration guide, repo guides); verdict `INHERITED`/`DEGRADED`/`BLOCKED`; exit codes `0`/`1`/`2`/`64`; D3 coexistence assertion that simulates emdash's `Stop:[emdashHook,userHook]` append (marker-based) and confirms Manifest hooks survive (FR-001–FR-005, FR-007); route errors via `err() { echo "emdash_inherit_check.sh: $*" >&2; }` and handle `--help` (≤15 lines, exit 0) before any config lookup (repo conventions).
- [x] T003 Make the probe executable and hygiene-clean: `chmod +x configs/claude/scripts/emdash_inherit_check.sh`, pass `shellcheck configs/claude/scripts/emdash_inherit_check.sh` (guards the shebang-non-exec + shellcheck CI gates).

**Checkpoint**: Probe exists and is contract-shaped — US1 and US3 can proceed.

---

## Phase 3: User Story 1 - Manifest config fully active in emdash sessions (Priority: P1) 🎯 MVP

**Goal**: Prove a Manifest-configured Claude Code agent launched by emdash inherits the full config (skills, subagents, hooks, MCP, guides) and that Manifest hooks survive emdash's injected hook wiring.

**Independent Test**: `bats tests/bats/emdash_inheritance.bats` passes against the fixtures; the manual smoke against the real emdash app confirms each dimension + hook firing under ACP.

### Tests for User Story 1

- [x] T004 [US1] Write `tests/bats/emdash_inheritance.bats` driving `emdash_inherit_check.sh --json --home tests/bats/fixtures/emdash/home --worktree tests/bats/fixtures/emdash/worktree`: assert every dimension D1–D6 is `PASS`, verdict `INHERITED`; assert `coexistence.manifest_hooks_preserved == true` after applying the **home** `settings.json.emdash-merged` variant (Manifest hooks are HOME-side — F3) AND `coexistence.worktree_permissions_intact == true` after the **worktree** `settings.local.json.emdash-merged` variant; add a `BLOCKED`-verdict case (missing `home/.claude`) asserting exit `2` (FR-011a, SC-001, SC-003). To faithfully reproduce emdash's launch env, export `EMDASH_HOOK_PORT`/`EMDASH_PTY_ID`/`EMDASH_HOOK_NONCE` in the probe invocation and assert their presence does NOT degrade resolution (the vars are represented in the `.emdash-merged` fixture's hook command; actual runtime env behavior is validated by the T007 manual smoke). Follows `deploy_antigravity.bats` conventions. [C2]

### Implementation for User Story 1

- [x] T005 [US1] Run `bats tests/bats/emdash_inheritance.bats`; iterate the probe (T002) and fixtures (T001) until green (evidence-before-assertion per repo verification norms).
- [x] T006 [US1] Register the inheritance check as this feature's Verify-gate smoke coverage (via `/smoke-manage` into `smoke-catalog/`, or a bats-tier entry) so CI runs the launch-env simulation as the critical-path smoke for the "run Manifest via emdash" workflow.
- [ ] T007 [US1] Execute the manual smoke from `quickstart.md` against the real emdash app with **Claude Code** (requires the installed emdash app + a live session): confirm skills/subagents/hooks/MCP/guides active and a Manifest hook FIRES under ACP mode; record results + the actual emdash-written `settings.local.json` shape in `specs/483-emdash-support/quickstart.md` (or a smoke-results note), and reconcile the T001 fixture if the real shape differs (FR-011b).

**Checkpoint**: US1 independently verifiable — the MVP (inheritance proven) is complete.

---

## Phase 4: User Story 2 - emdash worktrees are immediately functional (Priority: P2)

**Goal**: A fresh emdash worktree of this repo has its needed untracked files and a prepared environment, so tests/tooling run without manual fixup.

**Independent Test**: Create a fresh emdash worktree (or run `.emdash.json` `scripts.setup` in a clean checkout) → `bats tests/bats/` and `pytest tests/python/` pass with no manual setup.

- [x] T008 [P] [US2] Author repo-root `.emdash.json` per `contracts/emdash-project-config.md`: `preservePatterns` = `["guidance_local.yml"]` (the repo's only untracked local config; NOT `.env` — this repo has none and it is not gitignored here, spec-review F2); `scripts.setup` = `git submodule update --init --recursive` (bats helpers) + `pip install -r tests/requirements-ci.txt` (matches CI; NOT `uv sync` — this repo doesn't use uv for deps, spec-review F1), idempotent and fail-closed; `shellSetup` minimal. [F1][F2]
- [x] T009 [US2] Add a `.emdash.json` JSON-validity check to the config-validation step (CI `.github/workflows/ci.yml` and/or the repo's `python3 -c "import json..."` config checks) AND assert `preservePatterns` contains no tracked file (explicitly not `.claude/settings.local.json`) — depends on T008.
- [ ] T010 [US2] Verify a fresh worktree is functional: run `.emdash.json` `scripts.setup` in a clean checkout/worktree and confirm `bats tests/bats/` + `pytest tests/python/` pass with no manual fixup; confirm secret-bearing preserved files stay gitignored (SC-002, FR-006 AC3). Record result.

**Checkpoint**: US1 + US2 both independently functional.

---

## Phase 5: User Story 3 - Manifest recognizes, documents, and diagnoses emdash (Priority: P3)

**Goal**: env-check/config-audit and docs recognize emdash, validate the inheritance path, and surface the hook-coexistence caveat.

**Independent Test**: `/env-check` reports emdash presence + inheritance status (via the probe); `docs/EMDASH.md` lets a new user reach a working session unaided.

- [x] T011 [P] [US3] Add an "emdash Inheritance" section to `.skillshare/skills/env-check/SKILL.md` (new numbered check) that invokes `configs/claude/scripts/emdash_inherit_check.sh`, renders the per-dimension report, surfaces the `BLOCKED` (home-deploy-missing) prerequisite and the hook-coexistence caveat (FR-010, SC-005) — reuses the T002 probe. Opportunistic pre-existing fix while in this file (spec-review F4): remove the stale `.antigravity/scripts` and `.antigravity/prompts` entries from the Symlink Integrity expected-list (bootstrap prunes them as obsolete per commit 5e347fa, so they yield false env-check warnings). [F4]
- [x] T012 [P] [US3] Add an emdash hook-coexistence awareness note to `.skillshare/skills/config-audit/SKILL.md` (emdash appends its own `Stop` hook to `.claude/settings.local.json` + gitignores it; Manifest hooks are preserved; the machine-local injected hook should stay uncommitted) (FR-010).
- [x] T013 [P] [US3] Write `docs/EMDASH.md`: what emdash is; prerequisites (run `./bootstrap.sh` first, install a supported agent); setup; the `.emdash.json` pattern for other repos; the coexistence caveat (uncommitted injected hook, `.gitignore` interaction); Claude Code = verified, Codex/Gemini/Cursor = best-effort transitive; agents emdash launches that Manifest doesn't configure = out of guaranteed parity (FR-009, FR-012). Also document the remaining spec edge cases (FR-012 boundary/version basis): the **emdash release/version basis** for the guarantees [C6]; that **parallel worktrees may race on home-scoped settings writes** (emdash-internal; Manifest doesn't guard) [C1]; and that emdash **worktrees live outside the main checkout**, so any Manifest behavior assuming a main-checkout absolute path is a documented limitation [C1].
- [x] T014 [P] [US3] Add emdash pointers to the platform-facing docs: `README.md` ("running agents via emdash" → `docs/EMDASH.md`), `docs/GETTING_STARTED.md` ("Using Manifest with emdash" subsection), `AGENTS.md` (brief "emdash-launched agents inherit config transitively" note). Framed as a harness, NOT a deploy platform (FR-009).

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T015 Regenerate derived artifacts after the skill edits (T011/T012): run `configs/claude/scripts/generate_cursor_rules.sh` + the COMMANDS/GEMINI/AGENTS doc generators, and reconcile the end-of-file-fixer vs generated-`.mdc` double-newline interaction (per repo convention) so pre-commit is stable.
- [x] T016 [P] Assert SC-006 / FR-008 (filesystem-checkable): a bats (or CI) check confirming the feature creates NO `configs/emdash/` tree and that a home deploy produces NO `~/.emdash/` config dir. (The complementary claim "no `bootstrap/lib/*` / `agents/*.py` provider machinery modified" is a diff-scope assertion, not a runtime test — verify it in T017's `--from-ref origin/main` changed-file review.) [C3]
- [x] T017 Run the real pre-commit / CI mirror before opening the PR: `shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh`, `yamllint`, `bats tests/bats/`, `pytest tests/python/`, and the changed-file gate with `--from-ref origin/main`; fix any pre-existing-hygiene fallout (per the no-bypass-gate blast-radius lesson).
- [ ] T018 Run `quickstart.md` end-to-end and confirm every Success Criterion SC-001…SC-006; update the CLAUDE.md SPECKIT block to SHIPPED at merge and record the lifecycle outcome in `specs/483-emdash-support/`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: none — start immediately.
- **Foundational (P2)**: after Setup. T002 BLOCKS US1 + US3 (not US2).
- **US1 (P3)**: after Foundational (needs T002 probe + T001 fixtures).
- **US2 (P4)**: after Setup only — **independent of the probe**; can run in parallel with Foundational/US1.
- **US3 (P5)**: after Foundational (T011 reuses T002 probe); docs tasks otherwise independent.
- **Polish (P6)**: after the stories it touches (T015 after US3; T017/T018 after all).

### User Story Dependencies

- **US1 (P1)** → depends on Foundational; no dependency on US2/US3.
- **US2 (P2)** → depends only on Setup; fully independent (the one truly parallel story).
- **US3 (P3)** → depends on Foundational (probe) for T011; T012–T014 are independent docs.

### Within Each Story

- US1: T004 (test) defines acceptance → T005 iterates probe to green → T006 smoke coverage → T007 manual smoke (real app).
- US2: T008 (`.emdash.json`) → T009 (validity/tracked-file guard) → T010 (functional verify).
- US3: T011 (env-check) / T012 (config-audit) / T013 (docs) / T014 (pointers) all [P].

### Parallel Opportunities

- T001 (Setup) [P].
- **US2 (T008…T010) can proceed in parallel with Foundational + US1** — it's probe-independent.
- Within US3: T011, T012, T013, T014 are all different files → run in parallel.

---

## Parallel Example: User Story 3

```bash
# All US3 tasks touch different files — launch together:
Task: "Add emdash Inheritance section to .skillshare/skills/env-check/SKILL.md"        # T011
Task: "Add coexistence note to .skillshare/skills/config-audit/SKILL.md"               # T012
Task: "Write docs/EMDASH.md"                                                            # T013
Task: "Add emdash pointers to README.md, docs/GETTING_STARTED.md, AGENTS.md"           # T014
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup (T001) → Phase 2 Foundational (T002–T003) → Phase 3 US1 (T004–T007).
2. **STOP and VALIDATE**: `bats tests/bats/emdash_inheritance.bats` green + manual smoke confirms real-app inheritance. This proves the literal ask ("inherit all skills/agents/hooks").

### Incremental Delivery

1. MVP (US1) — inheritance proven + regression-protected.
2. + US2 — fresh emdash worktrees are functional (`.emdash.json`).
3. + US3 — env-check/config-audit/docs recognition.
4. Polish — regen derived files, CI mirror, SC-006 no-tree assertion, quickstart validation.

### Notes

- [P] = different files, no incomplete deps. [Story] = traceability to US1/US2/US3.
- **US2 is the parallelizable story** (probe-independent) — good candidate to run alongside US1.
- T007/T010/T018 need the **real emdash app** (and T007 a live agent session) — human/live steps, not fully CI-automatable; that is exactly why the design is hybrid (automated sim in CI + manual smoke).
- Editing `env-check`/`config-audit` SKILL.md triggers the cursor-rules + guide generators (T015) — regenerate + run the full pre-commit chain before the PR.
- Commit after each task or logical group.
