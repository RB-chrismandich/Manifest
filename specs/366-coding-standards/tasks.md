---
description: "Task list for Coding Standards & Edit-Time Enforcement"
---

# Tasks: Coding Standards & Edit-Time Enforcement

**Input**: Design documents from `specs/366-coding-standards/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — the repo requires bats coverage for `configs/claude/scripts/`
changes (CONTRIBUTING.md) and the constitution requires shell/Python tests.

**Organization**: Grouped by user story (US1=P1 … US4=P4) for independent delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- File paths are repository-relative.

## Path Conventions

Single project. Runtime artifact under `configs/claude/`; repo-infra at root
(`.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `pyproject.toml`,
`.editorconfig`, `docs/`); tests under `tests/bats/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared configuration the linters read across all layers.

- [X] T001 [P] [FR-013] Create root `pyproject.toml` with `[tool.ruff]` (select E,W,F,I,UP,B,C4,SIM,RUF; `ignore = ["E501"]` — ruff-format owns line length; line-length 88; `[tool.ruff.lint.per-file-ignores]` `"tests/**" = ["E402","S101"]`), `requires-python = ">=3.11"`, `[tool.pytest.ini_options]` (`addopts = "--strict-markers --strict-config"`), and `[tool.coverage.report]` `fail_under = 80` in `pyproject.toml`. (Select is the high-value subset; the noisier/unfixable groups N,S,A,DTZ,T20,RET,TCH,PTH were dropped so the changed-files gate doesn't fail on legacy debt — can be ratcheted up later.)
- [X] T002 [P] Add EditorConfig sections `[*.ps1]` (indent 4), `[*.mdc]` (indent 2), `[*.bats]` (indent 4) in `.editorconfig`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the pre-change baseline so config edits are verifiable.

- [X] T003 Capture a baseline: run `pre-commit run --all-files` against the current config and save output to `specs/366-coding-standards/baseline-precommit.txt` (records pre-existing failures to resolve under US4; do not commit secrets)

**Checkpoint**: Shared config in place; baseline known. User stories may begin.

---

## Phase 3: User Story 1 - In-session validation on every file edit (Priority: P1) 🎯 MVP

**Goal**: Every `Write|Edit` lints the edited file (`.sh/.py/.yml/.json/.md/.mdc`), advisory, non-blocking, fail-open, never mutating.

**Independent Test**: Feed a PostToolUse payload for a file with a known violation → advisory on stderr, `exit 0`, file unchanged; remove the linter from PATH → still `exit 0`.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [X] T004 [US1] Write bats tests in `tests/bats/lint_on_edit_hook.bats` asserting contract guarantees G1–G8 (exit-0 always, no file mutation, fail-open on missing tool, dispatch per extension, excluded-path skip, unknown-extension no-op, empty/bad payload, Bash 3.2 safety) per `contracts/edit-time-hook.md`

### Implementation for User Story 1

- [X] T005 [US1] Implement `configs/claude/scripts/lint_on_edit_hook.sh`: `#!/usr/bin/env bash`, `set -uo pipefail`, `--help` (≤15 lines), `err()` convention; parse PostToolUse JSON from stdin (`.tool_input.file_path` → `.file_path` via python3, mirroring `version_pin_hook.sh`); skip excluded prefixes (`.Jules/`, `node_modules/`, `.git/`, `templates/scaffold/`); extension dispatch table (`.sh`→`shellcheck --severity=info` (advisory; commit/CI use `warning`), `.py`→`ruff check --no-fix`, `.yml`/`.yaml`→`yamllint -f parsable`, `.json`→`python3 json.load`, `.md`/`.mdc`→`markdownlint -c .markdownlint.jsonc`); `command -v` guard per tool (fail-open); `_run` timeout wrapper (`timeout`→`gtimeout`→`perl` alarm→direct); advisory findings to stderr prefixed `lint-on-edit:`; **always `exit 0`**
- [X] T006 [US1] Mark the script executable (`chmod +x`) and wire it as a third `PostToolUse` `Write|Edit` hook (`~/.claude/scripts/lint_on_edit_hook.sh`) in `configs/claude/settings.local.json`
- [X] T007 [US1] Confirm deployment path: verify `bootstrap/lib/deploy.sh` copies `configs/claude/scripts/` (so the new script reaches `~/.claude/scripts/`) and preserves the executable bit; add to any explicit script manifest if one exists
- [X] T008 [US1] Lint & test the new script: `shellcheck --severity=warning configs/claude/scripts/lint_on_edit_hook.sh`, `tests/lint/check_array_expansion.sh`, and `npx bats tests/bats/lint_on_edit_hook.bats` (all pass)

**Checkpoint**: Edit-time advisory linting works end-to-end and is deployed. MVP complete.

---

## Phase 4: User Story 4 - Trustworthy, current enforcement tooling (Priority: P4, sequenced before US2)

> Implemented before US2 so that enabling the CI pre-commit gate (changed files) keeps `main` green. Independently testable via config audit + a local `pre-commit run --all-files` sweep.

**Goal**: No deprecated tools; current pins; guarded dormant-language hooks; Python type-check + `.mdc` coverage.

**Independent Test**: `grep terraform_tfsec .pre-commit-config.yaml` → none; revs match research §5; `pre-commit run --all-files` parses and dormant hooks skip.

### Implementation for User Story 4

- [X] T015 [US4] Bump `.pre-commit-config.yaml` revs to current: pre-commit-hooks `v6.x`, shellcheck-py `v0.11.x`, pre-commit-shfmt `v3.12.x` (add `-ln bash` to args), markdownlint-cli `v0.49.x`, yamllint `v1.38.x`, ruff-pre-commit `v0.15.x`, gitleaks `v8.30.x`, pre-commit-terraform `v1.101.x`
- [X] T016 [US4] In `.pre-commit-config.yaml` replace deprecated `terraform_tfsec` with `terraform_trivy`; add `terraform_fmt` and `terraform_validate` (all `types_or: [terraform]`, dormant/guarded)
- [X] T017 [US4] In `.pre-commit-config.yaml` bump golangci-lint to `v2.x` (`types_or: [go]`, dormant); add a guarded local Rust hook (`cargo fmt --check` + `cargo clippy -- -D warnings`, gated on `Cargo.toml` existence) — do NOT use the unmaintained `doublify/pre-commit-rust`
- [X] T018 [US4] In `.pre-commit-config.yaml` add a local `pyright` hook + `check-ast`/`debug-statements` (from pre-commit-hooks); widen markdownlint to also lint `configs/cursor/rules/*.mdc` (a `files:`-scoped invocation)
- [X] T019 [US4] Run `pre-commit run --all-files`; resolve violations introduced in changed files; confirm config parses (`python3 -c "import yaml,sys;yaml.safe_load(open('.pre-commit-config.yaml'))"`) and dormant Go/Rust/Terraform hooks are skipped (no matching files)

**Checkpoint**: Enforcement config is current, deprecation-free, and passes locally.

---

## Phase 5: User Story 2 - Standards cannot be bypassed (Priority: P2)

**Goal**: CI gate of record runs the full local check suite so uninstalled local hooks cannot bypass standards (incl. secret detection).

**Independent Test**: On a branch without local hooks, a planted ruff violation / secret fails the CI `lint` job.

### Implementation for User Story 2

- [X] T009 [US2] Add a `pre-commit (changed files)` step to the `.github/workflows/ci.yml` `lint` job: install `pre-commit`, cache `~/.cache/pre-commit` (key on `hashFiles('.pre-commit-config.yaml')`), and run it scoped to changed files — pull_request: `pre-commit run --from-ref "origin/$GITHUB_BASE_REF" --to-ref HEAD --show-diff-on-failure`; push: against the commit's `git diff` file list (guard for missing parent). Fetch base ref first.
- [X] T010 [US2] Keep existing whole-repo CI checks as additional coverage (do NOT remove the green scoped shellcheck/yamllint/markdownlint steps); the new changed-files pre-commit step adds ruff/shfmt/gitleaks/broad-markdownlint coverage on new code. Preserve all `test`/`validate` jobs.
- [X] T011 [US2] Validate the workflow: `yamllint .github/workflows/ci.yml` + `python3 -c yaml.safe_load`; confirm gitleaks and ruff run inside the changed-files pre-commit step (FR-007); confirm `test` job still enforces the ≥100-test floor. (Note: changed-files chosen over `--all-files` per the 2026-06-29 clarification — pre-existing debt.)

**Checkpoint**: The gate of record enforces everything local pre-commit does — no bypass path.

---

## Phase 6: User Story 3 - One authoritative, discoverable standard per language (Priority: P3)

**Goal**: Single `docs/CODING_STANDARDS.md` with per-language rules + scope verdict, linked from agent/contributor guides.

**Independent Test**: Open the doc; every named language has rules + an Active/Conditional/Document-only verdict; links from guides resolve.

### Implementation for User Story 3

- [X] T012 [US3] Author `docs/CODING_STANDARDS.md` with one section per language (Bash, Python, Markdown, YAML, JSON, bats, PowerShell, Go, Rust, Terraform), each listing rules, an Active/Conditional/Document-only verdict, and enforcing layers/tools; include repo-specific guarantees (macOS Bash 3.2 array safety, `err()`, `--help`) per FR-014; document the inline-exception policy (per-language suppression syntax + rationale required, blanket file-level disables discouraged) per FR-011; add a layered-enforcement overview table
- [X] T013 [P] [US3] Link `docs/CODING_STANDARDS.md` from `CLAUDE.md`, `.claude/CLAUDE.md`, `CONTRIBUTING.md`, and `AGENTS.md`
- [X] T014 [US3] Verify the new doc passes markdownlint (`.markdownlint.jsonc`) and is not excluded from enforcement

**Checkpoint**: Standards are documented, scoped, and discoverable.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T020 [P] Update `CONTRIBUTING.md` "Development Workflow" to reference the edit-time advisory hook and the CI pre-commit changed-files run as the authoritative gate (`--all-files` is a local full-sweep)
- [X] T021 Run `specs/366-coding-standards/quickstart.md` end-to-end (edit-time advisory demo, gate demo, currency greps) and fix any gaps
- [X] T022 Run the full suite: `npx bats tests/bats/` and `pytest tests/python/` — ensure ≥100 tests pass and local results match the CI changed-files `pre-commit run --from-ref/--to-ref`
- [X] T023 Constitution II gate: run `~/.claude/scripts/parallel_agent.py --review` (or equivalent ≥2-agent cross-verification) on the diff before opening the PR; record the verdict in the PR description

---

## Requirements Traceability

Every functional requirement and buildable success criterion maps to ≥1 task
(verified complete in `/speckit-implement-review`).

| Requirement | Task(s) |
|-------------|---------|
| FR-001 edit-time validate on every edit | T004, T005 |
| FR-002 no block / no mutate | T004 (G1/G2), T005 |
| FR-003 fail-open + time-bounded | T004 (G3/G8), T005 |
| FR-004 cover .sh/.py/.yml/.json/.md/.mdc, advisory | T004 (G4), T005 |
| FR-005 gate enforces local standards on changed code | T009, T011 |
| FR-006 gate runs pre-commit on changed files | T009 |
| FR-007 secret detection in the gate | T011 |
| FR-008 current tooling, no deprecated | T015, T016, T017, T018, T019 |
| FR-009 single standards doc w/ verdicts | T012, T013 |
| FR-010 dormant-language hooks guarded | T016, T017 |
| FR-011 inline exceptions, no blanket disable | T012 |
| FR-012 exclude generated/vendored paths | T005 (hook excludes), T016/T018 (config excludes) |
| FR-013 single Python config surface | T001 |
| FR-014 preserve repo guarantees (Bash 3.2, err(), --help) | T005, T012 |
| FR-015 retain four-layer model | T012 (documents), T005/T009 (extend) |
| SC-001/002/003 edit-time behavior | T004 (bats G1–G8), T005 |
| SC-004/007 no-bypass gate | T009, T011 |
| SC-005 no deprecated tools | T016, T019 |
| SC-006 documented verdict per language | T012 |
| SC-008 bounded edit-time overhead | T005 (timeout tiers) |

No orphan tasks: T002/.editorconfig and T003/baseline are foundational support;
T020–T023 are polish/verification (docs, quickstart, full suite, Constitution-II
cross-verification). T023 satisfies the constitution's parallel-agent gate.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1: T001–T002)**: no deps — start immediately.
- **Foundational (P2: T003)**: after Setup; informs US4.
- **US1 (P3 phase: T004–T008)**: independent (MVP). T004 before T005 (tests fail first); T005 before T006–T008.
- **US4 (T015–T019)**: independent; **sequenced before US2** to keep `main` green.
- **US2 (T009–T011)**: independent contract; best landed with/after US4 so CI passes.
- **US3 (T012–T014)**: fully independent.
- **Polish (T020–T023)**: after the targeted stories; T023 is the pre-PR cross-verification gate.

### Parallel Opportunities

- T001, T002 in parallel (different files).
- US1 (T004–T008) and US3 (T012–T014) can proceed in parallel — disjoint files.
- T013 is `[P]` (touches 4 distinct guide files, but each edit is small/independent).
- US4 then US2 should be sequential (US2 depends on US4's config being green).

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 baseline → 3. US1 (T004–T008) → **validate edit-time hook independently** → demo.

### Incremental Delivery

US1 (MVP) → US4 (currency) → US2 (no-bypass gate) → US3 (docs) → Polish. Each adds value without breaking prior stories.

## Notes

- `[P]` = different files, no dependencies. `[Story]` maps to spec user stories.
- Tests (T004) fail before T005 implementation.
- Commit after each task or logical group; keep `main` green by landing US4 before US2.
- The edit-time hook must NEVER block or mutate — re-assert G1/G2 after any change to T005.
