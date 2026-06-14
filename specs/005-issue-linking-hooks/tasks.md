---
description: "Task list for Issue-Linking Git Hooks implementation"
---

# Tasks: Issue-Linking Git Hooks

**Input**: Design documents from `/specs/005-issue-linking-hooks/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all authored in the design phase; `quickstart.md` must exist before T029 runs)

**Tests**: INCLUDED — the repo mandates `bats tests/bats/` for shell changes (`.claude/CLAUDE.md` Development Workflow) and the contracts define explicit testable guarantees (C1–C7, H1–H5). Tests are written to fail first, then implemented against.

**Organization**: Tasks grouped by user story. The shared engine lives in Foundational (both stories depend on it); each story is an independently testable increment on top.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = PR sync, US2 = commit sync, US3 = missing-issue creation
- All paths are repo-relative to the worktree root.

## Path Conventions

Shell-and-config layout (repo default). Engine + installer in `configs/claude/scripts/`; skills in `.skillshare/skills/`; config in `configs/claude/config/`; tests in `tests/bats/` + `tests/fixtures/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding and offline test fixtures

- [X] T001 Create directory scaffolding: `.skillshare/skills/pr-issue-sync/`, `.skillshare/skills/commit-issue-sync/`, `configs/claude/scripts/templates/`, `tests/fixtures/issue_support/`
- [X] T002 [P] Add offline mock fixtures (sample `pr-view`, `issue-view`, `issue-list` JSON payloads for github & gitlab) in `tests/fixtures/issue_support/`
- [X] T003 [P] Create `tests/bats/issue_support.bats` skeleton with `setup()`/`teardown()` that stubs `git_ops.sh`/`git_platform.sh` on `PATH` so tests run with no live tracker

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared issue-support engine — every primitive both stories delegate to

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create `configs/claude/scripts/issue_support.sh` skeleton: `set -euo pipefail`, `err()` helper, `--help` (≤15 lines, exit 0), subcommand dispatch for `sync-pr`/`sync-commit`/`resolve`
- [X] T005 Add `tool_policies.pr-issue-sync` (`enabled: false`, `hook_timeout_seconds: 5`) and `tool_policies.commit-issue-sync` (`enabled: false`, `hook_timeout_seconds: 5`, `commit_hook_mode: sync`) to `configs/claude/config/command_config.yml`
- [X] T006 Implement config loader in `configs/claude/scripts/issue_support.sh` (python3 YAML read, `label_sync.sh` precedent); `enabled: false` → clean no-op exit 0 (FR-015 runtime gate)
- [X] T007 Integrate platform detection via `git_platform.sh` in `issue_support.sh`; non-github/gitlab (plain `git`/none) → informational no-op exit (Edge: no platform)
- [X] T008 Implement `resolve` subcommand in `issue_support.sh`: precedence branch-prefix → pr-body → commit-message references **and** trailers (inline `#N`/`Fixes #N` plus `Issue:`/`Refs:` trailers, per R3/FR-004), validate each candidate via `git_ops.sh issue-view` (`exists` gate), emit `IssueRef[]` JSON; report ambiguous/conflicting candidates without auto-picking (FR-012)
- [X] T009 Implement fail-open timeout wrapper in `issue_support.sh` (R6/FR-008): bound tracker work by `hook_timeout_seconds` via `timeout`/`gtimeout` (or `bootstrap/lib/platform.sh` helper); any failure/timeout → single `err()` warning + exit 0 (guarantee C1). Distinguish two edge cases in the warning text: (a) **insufficient token scope** → report the specific missing capability (e.g. "token lacks issue-write scope") rather than a generic error (spec Edge L80); (b) **rate limiting** → detect throttle responses and back off (bounded retry within `hook_timeout_seconds`) before degrading to a warning (spec Edge L86)
- [X] T010 Implement forward-only transition primitive in `issue_support.sh` (data-model state machine / FR-006a): ordered set `planned<in-progress<needs-review<done`, no-op if issue already ≥ target (C5), skip closed/locked with warning (FR-013/C4)
- [X] T011 Implement idempotent back-link comment primitive in `issue_support.sh`: embed marker `<!-- issue-support:sync v1 ... -->`, skip/refresh if marker already present (R2/FR-007/C2) via `git_ops.sh issue-comment`/`issue-comment-edit-last`
- [X] T012 Implement run-summary emitter in `issue_support.sh`: one stdout line per `SyncAction` (`type target [result] (reason)`) plus `--json` form (FR-014); wire `--dry-run` prefix

**Checkpoint**: Engine primitives ready — user stories can now be implemented in parallel

---

## Phase 3: User Story 1 - Auto-sync the linked issue when a PR is opened (Priority: P1) 🎯 MVP

**Goal**: Opening a PR/MR back-links and advances each linked issue to `needs-review` and ensures the closing keyword, fail-open.

**Independent Test**: Open a PR on a branch tied to a known issue → issue gets a back-link comment, label → `needs-review`, and a missing `Closes #N` is appended — with no manual issue edits and no blocked PR.

### Tests for User Story 1

- [X] T013 [P] [US1] Add bats cases in `tests/bats/issue_support.bats` for `sync-pr`: resolves issue from PR, transitions → `needs-review`, idempotent re-run yields only `skipped` (C2), fail-open on tracker error exits 0 (C1), closed/locked issue skipped (C4), multi-issue PR acts on each (C7). Also cover the PR-installer (T017): idempotent re-install adds no duplicate entry (H1), disabled-config install is a no-op (H3), engine does not fire when the underlying command failed (H4)

### Implementation for User Story 1

- [X] T014 [US1] Add minimal `pr-edit <N>` subcommand to `configs/claude/scripts/git_ops.sh` (wraps `gh pr edit --body` / `glab mr update --description`), update its `--help`; non-destructive body append. Because `pr-edit` is a permanent public `git_ops.sh` primitive, add direct bats cases in `tests/bats/git_ops.bats` (append on github, append on gitlab, idempotent when keyword already present, graceful failure when the PR is not editable) — not only transitive coverage via `sync-pr`
- [X] T015 [US1] Implement `sync-pr <PR_NUMBER> [--dry-run] [--no-create]` in `configs/claude/scripts/issue_support.sh`: resolve → for each open issue transition → `needs-review` (T010), back-link comment (T011), ensure `Closes #N` via `git_ops.sh pr-edit` appending when missing (FR-005); all wrapped fail-open (T009)
- [X] T016 [US1] Create `.skillshare/skills/pr-issue-sync/SKILL.md` with `name`/`description` frontmatter; document `sync-pr` invocation, the PostToolUse trigger, fail-open behavior, and `--no-create`
- [X] T017 [US1] Create `configs/claude/scripts/install_issue_hooks.sh` with `--help`, `--enable`/`--remove`, and the unified PR PostToolUse matcher (`pr-create`|`gh pr create`|`glab mr create` → `sync-pr <N>`) via `ai-hooks-integration`; idempotent re-install (H1), opt-in no-op when not enabled (H3), fires only on the underlying command's success (H4)
- [X] T018 [US1] Register `pr-issue-sync` per `.claude/CLAUDE.md` "Adding New Skills": add `parallel_agents`/`validation_tier` under `tool_policies.pr-issue-sync` in `command_config.yml`; verify `configs/claude/skills` symlink is intact (not replaced)

**Checkpoint**: PR-open sync works end-to-end and is independently demoable (MVP)

---

## Phase 4: User Story 2 - Auto-sync the linked issue on branch commits (Priority: P2)

**Goal**: Committing to a feature branch advances a `planned` issue to `in-progress`, de-duplicated across commits, fail-open.

**Independent Test**: Commit to a branch tied to a `planned` issue → issue moves to `in-progress` exactly once across multiple commits; commits never blocked.

### Tests for User Story 2

- [X] T019 [P] [US2] Add bats cases in `tests/bats/issue_support.bats` for `sync-commit`: resolves from branch prefix/commit trailer, `planned`→`in-progress`, 10 consecutive commits transition/comment at most once (C2/SC-003), fail-open exits 0 (C1), `commit_hook_mode: background` falls back to `sync` with a warning (FR-016). Also cover the native installer (T022): refuses to clobber a pre-existing foreign `post-commit` hook (H2), and `--remove` cleanly removes both the PostToolUse entry and the delimited native block (H5). Add a recovery case (FR-017): after a first run that times out / fails mid-way (tracker error injected), a second run brings the issue to the correct state with no duplicate comment or double transition

### Implementation for User Story 2

- [X] T020 [US2] Implement `sync-commit <SHA|HEAD> [--dry-run] [--no-create]` in `configs/claude/scripts/issue_support.sh`: resolve → transition `planned` → `in-progress` (only issues already carrying the `planned` label; unlabeled issues are outside the managed lifecycle and left untouched, per FR-006) → dedup back-link comment; read `commit_hook_mode` and on `background` fall back to `sync` + `err()` warning (v1; reserved value per FR-016)
- [X] T021 [US2] Create `.skillshare/skills/commit-issue-sync/SKILL.md` with `name`/`description` frontmatter; document `sync-commit`, the commit trigger, dedup/idempotency, and fail-open
- [X] T022 [US2] Extend `configs/claude/scripts/install_issue_hooks.sh`: unified commit PostToolUse matcher (`git commit` → `sync-commit HEAD`) plus `--native` guarded `post-commit` installer (refuses to clobber a foreign hook H2, writes a delimited managed block) and `--remove` cleanup of both surfaces (H5)
- [X] T023 [US2] Register `commit-issue-sync` per "Adding New Skills": add `parallel_agents`/`validation_tier` under `tool_policies.commit-issue-sync` in `command_config.yml`

**Checkpoint**: Commit sync and PR sync both work independently

---

## Phase 5: User Story 3 - Offer to create a tracking issue when none is linked (Priority: P3)

**Goal**: When no issue resolves, offer (on confirmation) a best-of-breed tracking issue: dedup-checked, templated, canonically labeled, linked back.

**Independent Test**: Trigger a PR/commit on a branch with no issue association → a pre-filled issue is proposed; created only on confirm (non-interactive → no-create + warn); a pre-existing match is reused, not duplicated.

### Tests for User Story 3

- [X] T024 [P] [US3] Add bats cases in `tests/bats/issue_support.bats` for the create flow: dedup-match reuses an existing open issue instead of creating (FR-009a), non-interactive context defaults to no-create + warn (FR-009), template renders with context/acceptance-criteria/links and applies `planned` label (FR-009b/c)

### Implementation for User Story 3

- [X] T025 [P] [US3] Create engine-owned template `configs/claude/scripts/templates/issue_support_issue.md`: context summary, acceptance-criteria stub, bidirectional links to branch/PR/commit
- [X] T026 [US3] Implement create-issue flow in `configs/claude/scripts/issue_support.sh`: dedup search via `git_ops.sh issue-list` (title/branch match) → interactive confirm (non-interactive → no-create + warn) → render template (T025) → `git_ops.sh issue-create` with `planned` label → link back → re-run the normal sync so the new issue enters the lifecycle (FR-009/009a/009b/009c)
- [X] T027 [US3] Wire `--no-create` flag + interactive-context detection into `sync-pr`/`sync-commit` in `issue_support.sh`; document the create-on-confirm behavior in both `SKILL.md` files

**Checkpoint**: All three user stories independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Docs, verification, and the constitution-required review gate

- [ ] T028 [P] Update `docs/COMMANDS.md` (and README skills note) to document `pr-issue-sync` + `commit-issue-sync` and `install_issue_hooks.sh`
- [ ] T029 Run `quickstart.md` steps 2–6 end-to-end against a scratch repo (commit trigger, PR trigger, missing-issue creation, fail-open, dry-run)
- [ ] T030 Run verification gate: `shellcheck configs/claude/scripts/issue_support.sh configs/claude/scripts/install_issue_hooks.sh configs/claude/scripts/git_ops.sh`; `yamllint configs/claude/config/command_config.yml`; `bats tests/bats/issue_support.bats`. Assert FR-010 label conformance: every label the engine sets or applies to a created issue exists in `configs/claude/config/labels.yml` (grep the engine's label literals against the registry — no off-registry labels)
- [ ] T031 Tier 1 cross-verification (Constitution II): run `parallel_agent.py --review` on the `issue_support.sh` + `git_ops.sh` diff (token handling + >200 lines) before opening the PR

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories** (it is the shared engine)
- **User Stories (Phase 3–5)**: All depend on Foundational. US1 → US2 → US3 in priority order, or parallel if staffed (different SKILL.md files; engine edits are additive subcommands)
- **Polish (Phase 6)**: Depends on the desired user stories being complete

### Within Foundational (ordering)

- T004 (skeleton) → T006 (config loader) → T007 (platform) → T008 (resolve) → T009 (timeout) → T010/T011 (transition/comment primitives) → T012 (summary). T005 (config entries) can land any time before T006.

### User Story Dependencies

- **US1 (P1)**: Foundational only. T014 (`pr-edit`) before T015 (`sync-pr` uses it). T016/T017/T018 after T015.
- **US2 (P2)**: Foundational only. T020 (`sync-commit`) before T022 (installer wires it). Independent of US1.
- **US3 (P3)**: Foundational + at least one sync path. T025 (template) before T026 (create flow). T027 touches both SKILL.md files (coordinate if US1/US2 in flight).

### Parallel Opportunities

- Setup: T002, T003 in parallel.
- US1 tests T013 ∥ US2 tests T019 ∥ US3 tests T024 (all author against the engine contract; different test cases).
- T025 (template, static asset) parallel with US3 logic authoring.
- Across stories: US1 and US2 are implementable by different developers immediately once Foundational is done (distinct subcommands/skills). US3 can begin **test authoring** (T024) and its static **template** (T025) in parallel too, but its **implementation T026/T027 is blocked** until at least one sync path lands (T015 `sync-pr` **or** T020 `sync-commit`) — T026 explicitly re-runs the normal sync, a runtime call back into that path.
- Shared touch-points are serialized, not parallel: `command_config.yml` (T018/T023) and the two SKILL.md files (T027 edits both).

---

## Parallel Example: User Story 1

```bash
# After Foundational completes — author US1 tests and the new git_ops primitive together:
Task: "T013 [US1] bats cases for sync-pr in tests/bats/issue_support.bats"
Task: "T014 [US1] add pr-edit subcommand to configs/claude/scripts/git_ops.sh"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup
2. Phase 2: Foundational (shared engine — CRITICAL, blocks everything)
3. Phase 3: User Story 1 (PR sync)
4. **STOP and VALIDATE**: run quickstart step 3 + `bats tests/bats/issue_support.bats` for US1
5. Demo/enable on one repo (`install_issue_hooks.sh --enable`)

### Incremental Delivery

1. Setup + Foundational → engine ready
2. US1 (PR sync) → test → enable (MVP)
3. US2 (commit sync) → test → enable
4. US3 (missing-issue creation) → test → enable
5. Polish (docs, verification, Tier 1 review gate)

### Notes

- [P] = different files, no incomplete dependencies.
- All engine subcommands MUST exit 0 (fail-open) — verify in every bats case.
- Shared touch-points (`command_config.yml`, both `SKILL.md`) are serialized, not [P].
- Commit after each task or logical group; run `shellcheck`/`bats` before each commit (repo convention).
- Do NOT replace the `configs/claude/skills` symlink with a real directory.
