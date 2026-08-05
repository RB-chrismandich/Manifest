# Tasks: Deploy Reconciliation Review (Orphan Detection)

**Input**: Design documents from `specs/368-deploy-orphan-review/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: Test tasks are INCLUDED — the spec defines explicit acceptance scenarios and SCs,
and Constitution Principle VI mandates a smoke test (the Verify gate) for the shipped
user-facing workflow. `bats` is the primary harness (repo convention for shell/deploy logic).

**Organization**: Grouped by user story (US1 preview → US2 deploy report → US3 removal) on top
of a shared foundational reconcile engine. Authoritative interface = `contracts/reconcile-cli.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependency)
- **[Story]**: US1 / US2 / US3 (omitted for Setup / Foundational / Polish)

## Path Conventions

Single project (config-management repo): runtime artifacts under `configs/` and
`.retired skill supply/skills/`; bootstrap integration in `bootstrap/`; tests in `tests/bats/`
(+ optional `tests/python/`); smoke catalog in `smoke-catalog/` (repo root).

---

## Phase 1: Setup (Shared Scaffolding)

**Purpose**: Create the file skeletons all later work fills in.

- [x] T001 Create `configs/claude/scripts/deploy_reconcile.sh` skeleton: shebang, `set -euo pipefail`, bash-3.2-safe, `err() { echo "deploy-reconcile: $*" >&2; }`, `usage()`/`--help` (≤15 lines, **exits 0 before any config/home/project/dependency lookup** per cli-help-before-dependency-checks), and a full argument parser for every flag in `contracts/reconcile-cli.md` §3 (`--remove --yes --json --project --home --root --config --protect --backup-dir --help`); `chmod +x`.
- [x] T002 [P] Create `configs/claude/config/reconcile.yml` — the protection policy: a flat `reconcile.protected:` glob list seeded from research Topic 2 / data-model §6 defaults (settings.json, settings.local.json, .credentials.json, .agent_outputs, projects, plugins, commands, ide, sessions, tasks, todos, shell-snapshots, statsig, cache, backups, security, history.jsonl, *.jsonl, .last-*, .plans, plans, .deployed-skills; secondary-home auth.json, oauth_creds.json, *.log). Header MUST document that `*` spans `/` and that the policy is additive-only.
- [x] T003 [P] Create `.retired skill supply/skills/deploy-reconcile/SKILL.md` scaffold with `name: deploy-reconcile` + a triggering `description` frontmatter (body filled in T014).

---

## Phase 2: Foundational (Blocking — the reconcile engine, shared by US1/US2/US3)

**Purpose**: The detection/classification core. ⚠️ No user story can complete until this is done.

- [x] T004 In `configs/claude/scripts/deploy_reconcile.sh`: managed-root + `--home`/`MANIFEST_RECONCILE_HOME` resolution (5 roots: `.claude` canonical + `.cursor/.gemini/.codex/.antigravity`) and deployable-unit enumeration at unit granularity — skills = top-level dirs under `<root>/skills`, configs = individual files under `<root>/config`, plus per-home real artifacts (`.cursor/rules/*.mdc`, `mcp.json`; `.gemini/GEMINI.md`, `settings.json`; `.codex/AGENTS.md`). Hard-exclude `~/.claude/.agent_outputs` and the trash root (FR-013/FR-018/FR-009).
- [x] T005 Portable canonicalization + cross-home dedup: resolve each unit with `python3 os.path.realpath` (never `readlink -f`), key the report by canonical path so a shared symlinked target collapses to one entry; skip/report dangling links, never crash (FR-017). Depends: T004.
- [x] T006 Project-source ("expected set") resolution: `--project`/`MANIFEST_REPO`/auto-detect a git repo containing `configs/claude/` (else **exit 2**); enumerate what the project would currently deploy (skills from `.retired skill supply/skills`, configs from `configs/claude` + `configs/<assistant>`) honoring `services.yml` toggles, graphify gating, and merge-vs-full mode (FR-001; research Topic 5). Depends: T004.
- [x] T007 Orphan determination: a deduped unit inside a managed root with no matching project source is an orphan; MUST NOT descend into a skill that still has a project source (FR-001/FR-009/FR-018). Depends: T005, T006.
- [x] T008 Protection-policy loader + matcher: union of hardcoded guards (trash dir + reconcile config files) + repeatable `--protect` + machine-local `${MANIFEST_RECONCILE_CONFIG:-$MANIFEST_STATE_ROOT/reconcile.local.yml}` + `reconcile.yml` (`RECONCILE_CONFIG` else `$SCRIPT_DIR/../config/reconcile.yml`); match each unit's root-relative path via `fnmatch.fnmatchcase` with `*` spanning `/`; additive → KEEP (FR-007/FR-014/SC-004). Depends: T007.
- [x] T009 Bounded active-dependent detection: `find <secondary-home> -mindepth 1 -maxdepth 2 -type l` over only the 4 secondary homes (~20 edges, never a filesystem walk); a canonical target with an active edge resolving to/into it is KEEP "shared target — active dependents"; broken links are not dependents (FR-008/FR-015/FR-016/SC-006). Depends: T005.
- [x] T010 Classification precedence assembling the Reconciliation Report (in-memory): hardcoded guard → `protected` → `shared_active_dependents` → else `orphan_no_source` (REMOVE); attach reason + reason_code per data-model §5 / contract §7 (FR-002). Depends: T008, T009.

---

## Phase 3: User Story 1 — On-demand preview (Priority P1) 🎯 MVP

**Goal**: A maintainer runs the review and gets a read-only KEEP/REMOVE list + summary.
**Independent test**: Delete a skill from the project, run preview → it appears under REMOVE with an accurate count and nothing on disk changes (quickstart Step 1).

- [x] T011 [US1] Human-readable preview output in `deploy_reconcile.sh` per contract §5: `KEEP (N)` section first, then `REMOVE (N)`, tilde-abbreviated canonical paths, stable reason strings, and the exact summary line `Summary: N orphans  |  K KEEP  |  R REMOVE` (the deploy hook + bats grep this) (FR-003/FR-004/SC-001/SC-007). Depends: T010.
- [x] T012 [US1] `--json` output per contract §7 canonical schema (`mode/project/roots/summary{orphans,keep,remove}/items[]/removed/backup_dir`; flattened items with `unit_type`, `verdict`, `reason_code`, `matched_pattern`, `dependents`) (FR-004). Depends: T010.
- [x] T013 [US1] Exit-code semantics per contract §8: 0 for preview/clean/orphans-found (orphans NEVER nonzero), 2 for usage/unresolvable project / `--backup-dir` inside a managed root; clean state prints the "no orphans" result (FR-012). Depends: T011, T012.
- [x] T014 [P] [US1] Fill `.retired skill supply/skills/deploy-reconcile/SKILL.md` body per contract §11 (Preview → Apply-with-confirm → Review-outcome → Safety), modeled on `branch-clean`.
- [x] T015 [P] [US1] Register `tool_policies.deploy-reconcile` in `configs/claude/config/command_config.yml` (allowed Read/Glob/Grep/Bash; `parallel_agents` conditional — Tier 1 on `--remove`; `subagents` never; validation_tier 1; no validation_criteria override) and regenerate ALL derived docs via `generate_commands_doc.py` (`docs/COMMANDS.md` incl. its command-count, plus the per-platform Gemini/Codex/Cursor guide command tables — never hand-edit). The new skill increments the command count and may shift the context budget → re-run `tests/bats/context_budget.bats` and bump the budget/headroom comment if needed (token-economy-context-rules / shared-budget gotcha).
- [x] T016 [US1] `tests/bats/deploy_reconcile.bats` (create) — cases: `--help` exits 0 ≤15 lines before any lookup; dry-run non-mutation via before/after checksums (SC-002); project-present unit not listed (FR-001); REMOVE classification + counts + `--json` shape (FR-002/SC-003/FR-004); managed-scope boundary — out-of-root file never reported (FR-009/FR-013); clean state → "no orphans" (FR-012); missing `~/.claude` → 0 orphans exit 0. Uses a hermetic mktemp `--home`/`--project` fixture. Depends: T011–T013.

**Checkpoint**: US1 is independently shippable — read-only, safe, delivers the core "list kept/removed" ask.

---

## Phase 4: User Story 2 — Deploy-time report (Priority P2)

**Goal**: The review runs automatically (report-only) during deploy.
**Independent test**: With an orphan present, run the deploy/write step → the KEEP/REMOVE summary prints and the deploy still succeeds without deleting anything (quickstart Step 6).

- [x] T017 [US2] Add fail-open `reconcile_deploy_report()` to `bootstrap/lib/deploy.sh` per `contracts/deploy-integration.md`: runs `deploy_reconcile.sh --project "$SCRIPT_DIR"` **preview-only** (never `--remove`), prints the one-line KEEP/REMOVE summary, swallows all errors (FR-005/FR-006). Depends: T011.
- [x] T018 [US2] Wire the guarded call in `bootstrap.sh main()` immediately after `deploy_configs` (+ `after_deploy` hook), before `verify_installation`: `reconcile_deploy_report || print_warning "reconcile review skipped (non-fatal)"`; MUST NOT contribute to `verify_errors` so bootstrap still exits non-zero only on real verify failure (P-V). Depends: T017.
- [x] T019 [US2] Add bats case (in `deploy_reconcile.bats` or `tests/bats/deploy_skills.bats` neighbor): forced reconcile error during deploy → WARN printed, deploy succeeds, nothing deleted, no backup dir created, normal summary prints (research Topic 6 case 15; US2-AC1/2/3, P-V). Depends: T017, T018.

**Checkpoint**: Drift is surfaced at deploy time, fail-open.

---

## Phase 5: User Story 3 — Opt-in recoverable removal (Priority P3)

**Goal**: After preview, the user opts in and only REMOVE items are moved to a recoverable backup.
**Independent test**: With one REMOVE + one KEEP item, run `--remove --yes` → only REMOVE is moved to the timestamped backup, KEEP remains, and `restore.sh` brings it back (quickstart Steps 3–4).

- [x] T020 [US3] Confirm gate in `deploy_reconcile.sh`: `--remove` prints the REMOVE list + target backup dir, then requires an affirmative `/dev/tty` answer OR `--yes`/`RECONCILE_ASSUME_YES=1`; without confirmation nothing is moved (FR-010/FR-011/US3-AC2). Depends: T010.
- [x] T021 [US3] Recoverable move: resolve trash root `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/reconcile-trash/<RUN_TS>/` (`--backup-dir`/`MANIFEST_RECONCILE_TRASH`; `MANIFEST_RECONCILE_TS` test-only; refuse exit 2 if inside any managed root); move each REMOVE item to `<RUN_TS>/<home-tag>/<rel>` via `mv` with an `rsync -a` + verified-`rm` EXDEV fallback; act on the **canonical** path only; KEEP untouched; `chmod 700` (FR-010/SC-005/SC-008). Depends: T020.
- [x] T022 [US3] Restore artifacts: write `removed.tsv` + generate `restore.sh` (restores canonical paths first so secondary symlinks re-resolve) into the backup dir; report the backup location + restore command; populate `--json` `removed`/`backup_dir` (FR-010/SC-008). Depends: T021.
- [x] T023 [US3] bats cases: backup+restore recoverable (SC-008); only REMOVE moved, KEEP untouched (SC-005); backup excluded from scope — second run never re-reports (edge); dedup — one symlinked orphan reported once (FR-017); shared-target active-dependent KEEP (FR-008/FR-015); deployable-unit no-descend (FR-018); `--remove` without confirm/`--yes` removes nothing (FR-011). Depends: T020–T022.

**Checkpoint**: Full feature — preview, deploy report, and recoverable cleanup.

---

## Phase 6: Polish & Verify Gate (Cross-Cutting)

- [x] T024 Create `smoke-catalog/manifest.yaml` (repo's FIRST catalog): app `manifest`, tier `Lite`, type `cli` — run the deployed `deploy_reconcile.sh --home <fixture> --project <fixture> --json` against a hermetic temp fixture, `expect_exit: 0`, `captures` regex on the `Summary:`/JSON summary. **This is the P-VI Verify gate — required, non-skippable.**
- [x] T025 Wire CI to run `smoke_test.py run --app manifest --tier Lite` (`.github/workflows/ci.yml`) with the correct `--catalog-dir`, and keep the existing test floor green.
- [x] T026 [P] (Conditional) If classification is factored into a `python3` helper, add `tests/python/test_reconcile_policy.py` (pattern-match, realpath-dedup, active-dependent as pure functions). Skip with a rationale if logic stays in Bash.
- [x] T027 Lint/format gate: `shellcheck configs/claude/scripts/deploy_reconcile.sh bootstrap/lib/deploy.sh bootstrap.sh`; `yamllint configs/claude/config/reconcile.yml smoke-catalog/manifest.yaml`; run full `bats tests/bats/` + `pytest tests/python/`; confirm `docs/COMMANDS.md` regen is drift-clean. Run the REAL pre-commit (`--from-ref origin/main`) before opening the PR (no-bypass-gate blast-radius lesson).
- [x] T028 Execute `quickstart.md` end-to-end (all 7 steps) and confirm the per-step FR/SC coverage map passes (FR-001–FR-018, SC-001–SC-008).
- [x] T029 Constitution gate (P-II/P-III): cross-verify the implementation diff with `parallel_agent.py` (Tier 1 — destructive removal + security) before opening the PR; record the consensus verdict.

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → no deps; T002/T003 parallel with T001.
- **Foundational (T004–T010)** blocks ALL user stories. Internal order: T004 → {T005, T006} → T007 → T008; T005 → T009; {T008,T009} → T010.
- **US1 (T011–T016)** depends on T010. MVP. T014/T015 parallel (different files).
- **US2 (T017–T019)** depends on T011 (needs the preview/summary output). Independent of US3.
- **US3 (T020–T023)** depends on T010 (classification). Independent of US2.
- **Polish (T024–T029)** after the stories it covers; T024/T025 need US1 (preview) at minimum; T029 is the final pre-PR gate.

## Parallel Opportunities

- Setup: T002 + T003 alongside T001.
- US1: T014 (SKILL.md) + T015 (command_config.yml/COMMANDS.md) run parallel to the T011–T013 script output work.
- US2 and US3 can proceed in parallel once Foundational completes (different concerns; US2 in bootstrap, US3 in the script's removal path) — though both touch `deploy_reconcile.sh`/its tests, so coordinate file edits.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: ships the read-only preview — the explicit core
  request — safely and independently.
- **Increment 2 = US2**: deploy-time report (fail-open).
- **Increment 3 = US3**: recoverable removal.
- **Always**: Phase 6 Verify gate (T024 smoke) must pass before any sub-task is marked complete
  (P-VI); the parallel-agent cross-verification (T029) gates the PR (P-II).

## Task count

29 tasks — Setup 3, Foundational 7, US1 6, US2 3, US3 4, Polish 6.
Independent test criteria per story are stated at each phase header.
