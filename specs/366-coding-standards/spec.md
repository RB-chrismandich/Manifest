# Feature Specification: Coding Standards & Edit-Time Enforcement

**Feature Branch**: `366-coding-standards`

**Created**: 2026-06-28

**Status**: Draft

**Input**: User description: "Research and Improve coding standards for languages Python, Rust, Go, Terraform, Bash, etc. Add explicit hooks whenever a file is edited / modified to ensure we appropriately review / validate the coding standard. Make the recommended changes." (accompanied by a proposed set of per-language "commandments" and a sample `.pre-commit-config.yaml`.)

> **Domain note**: This feature's subject matter *is* programming-language quality
> tooling, so language names (Python, Bash, …) and the concept of "standards
> checking / linting" are domain vocabulary, not implementation leakage. Specific
> tools, tool versions, and script names are deliberately deferred to the
> implementation plan. Supporting research lives in
> [research-notes.md](./research-notes.md).

## Clarifications

### Session 2026-06-28

- Q: Which file types should edit-time validation lint at launch (advisory/non-blocking)? → A: Widest set — `.sh`, `.py`, `.yml`/`.yaml`, `.json`, `.md`, and Cursor rule files (`.mdc`); advisory and non-blocking, matching the existing per-edit hooks.
- Q: How should the gate of record prevent local standards from being bypassed? → A: CI runs the full local check suite (`pre-commit run --all-files`) as the gate of record — one configuration, zero divergence.
- Q: What happens to enforcement hooks for languages with no real files (Go, Rust, Terraform)? → A: Keep them as guarded, version-current scaffold references that fire only when real sources appear (Trivy instead of the deprecated tfsec, golangci-lint v2, guarded cargo hooks).

### Session 2026-06-29

- Q: Implementation revealed CI never ran most linters, so `pre-commit run --all-files` would fail on substantial pre-existing debt (39+ ruff errors today, plus unmeasured shfmt/markdownlint debt). How should the gate of record handle pre-existing debt? → A: The CI gate runs pre-commit against the files **changed in the PR/push** (not `--all-files`). This closes the bypass for all new and modified code (the intent of SC-007) without a high-risk repo-wide retro-cleanup; pre-existing debt is fixed opportunistically as files are touched, and existing whole-repo CI checks (scoped shellcheck/yamllint/markdownlint) are retained as additional coverage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - In-session validation on every file edit (Priority: P1)

As a contributor or AI coding agent editing a file in this repository, when I
create or modify a file, that file is immediately checked against its language's
coding standard and any violation is surfaced to me **in the same working
session** — without blocking my work and without silently changing the file.

**Why this priority**: This is the user's explicit core request ("add explicit
hooks whenever a file is edited / modified"). Today the only enforcement layer
that fires on every edit performs no language checking, so violations are
discovered minutes later at commit or in CI. Catching them at the moment of
authorship is the single highest-value change and is independently shippable.

**Independent Test**: Edit a file of each primary language so it contains a known
standards violation; confirm a clear advisory message identifying the file and the
violation appears in-session, the edit is not blocked, and the file content on
disk is unchanged.

**Acceptance Scenarios**:

1. **Given** a primary-language file, **When** a standards violation is written
   into it, **Then** an advisory message naming the file and the issue is surfaced
   in the same session and the edit operation still completes successfully.
2. **Given** the required checking tool is not installed, **When** a file is
   edited, **Then** the edit completes normally with no error and no spurious
   failure (fail-open).
3. **Given** a file is edited, **When** the standards check runs, **Then** the
   file's on-disk contents are not modified by the check (no auto-fix at edit time).
4. **Given** a non-source file, or a language with no active standard, **When** it
   is edited, **Then** no irrelevant warnings are produced.

---

### User Story 2 - Standards cannot be bypassed (Priority: P2)

As a maintainer, I want the project's gate of record (the checks that run on every
pull request) to enforce the same standards as the local checks, so that a
contributor who has not installed the local hooks cannot land code that violates
the standards.

**Why this priority**: Several standards (Python lint/format, shell formatting,
secret detection, broad documentation linting) currently run only locally and are
bypassable by skipping local-hook installation. Closing this divergence protects
the main branch regardless of local setup. Deliverable independently of the
edit-time work.

**Independent Test**: On a branch without local hooks installed, introduce a
Python lint violation, a formatting drift, and a planted secret; open a pull
request; confirm the gate of record fails for each.

**Acceptance Scenarios**:

1. **Given** local hooks are not installed, **When** a change introduces a
   primary-language standards violation, **Then** the gate of record fails and
   identifies the violation.
2. **Given** a committed secret, **When** the gate runs, **Then** secret detection
   fails the gate.
3. **Given** the gate-of-record definition, **When** audited, **Then** every
   standard enforced locally for a primary language is also enforced by the gate
   (or the gate runs the local suite directly).

---

### User Story 3 - One authoritative, discoverable standard per language (Priority: P3)

As a contributor or agent, I want a single committed document that states the
coding standard for each language and whether it is actively enforced,
conditionally enforced, or documented-only in this repo, so expectations are
explicit and discoverable.

**Why this priority**: Standards are currently scattered across `CLAUDE.md`,
`CONTRIBUTING.md`, and `.editorconfig`. A single source with an explicit
enforcement-scope verdict per language prevents confusion (e.g., "why is there a
Rust rule when there is no Rust code?").

**Independent Test**: Open the standards document; confirm it lists each in-scope
language with its rules and an Active/Conditional/Document-only verdict, and that
it is linked from the repo's agent/contributor guides.

**Acceptance Scenarios**:

1. **Given** the standards document, **When** a reader looks up any named
   language, **Then** they find its rules and an enforcement-scope verdict.
2. **Given** the document, **When** referenced from the contributor/agent guides,
   **Then** the links resolve.

---

### User Story 4 - Trustworthy, current enforcement tooling (Priority: P4)

As a maintainer, I want deprecated and stale enforcement tools remediated so the
gates actually run and produce current results.

**Why this priority**: A deprecated security scanner and a major-version-behind
linter produce stale or no results, eroding trust in the gates. Dead checks for
absent languages add noise.

**Independent Test**: Audit the enforcement configuration; confirm no deprecated
tool remains, pinned versions are within the currency policy, and each configured
check either has files to act on or is explicitly marked dormant.

**Acceptance Scenarios**:

1. **Given** the enforcement configuration, **When** audited, **Then** no
   deprecated tool is present and a current replacement is configured.
2. **Given** a configured check with no matching files, **When** a normal change
   is committed, **Then** it does not run spuriously and is documented as dormant.

---

### Edge Cases

- An edit-time check tool is missing/uninstalled → fail open; the edit proceeds.
- An edit-time check exceeds its time budget → it is bounded and abandoned without
  blocking or stalling the edit.
- A file legitimately needs a rule exception → an inline, justified suppression is
  supported; blanket file-level disables are not the norm.
- A language has zero real files (Rust/Go/Terraform) → its standard is documented
  but no active gate fires; a guard prevents the tool erroring on an empty
  workspace.
- Generated/vendored/excluded paths (e.g., `.Jules/`, `node_modules/`, scaffold
  templates) are not subject to enforcement.
- macOS Bash 3.2 + `set -u` empty-array expansion remains caught (existing repo
  constraint must be preserved).
- A file type without an active edit-time standard (`.bats`, `.ps1`) → behavior is
  explicitly decided (commit/CI coverage or documented exclusion) rather than
  silently unenforced.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (P1): On every in-session file create/modify action, the system MUST
  validate the affected file against its language's standard for the designated
  primary languages and surface any violation in-session.
- **FR-002** (P1): Edit-time validation MUST NOT block the edit and MUST NOT modify
  file contents (no auto-fix at edit time).
- **FR-003** (P1): Edit-time validation MUST fail open — a missing tool or a check
  error MUST NOT cause the edit to fail — and MUST be time-bounded so a slow check
  cannot stall the session.
- **FR-004** (P1): Edit-time validation MUST cover `.sh`, `.py`, `.yml`/`.yaml`,
  `.json`, `.md`, and Cursor rule files (`.mdc`), and MUST be advisory and
  non-blocking, consistent with the existing per-edit hooks. Other file types are
  out of edit-time scope until a standard is defined for them.
- **FR-005** (P2): The gate of record (pull-request checks) MUST enforce, for every
  primary language, the same standards enforced by the local commit-time checks on
  the code changed in the PR/push, such that uninstalled local hooks cannot bypass
  them for new or modified code.
- **FR-006** (P2): The gate of record MUST satisfy FR-005 by running the same
  `.pre-commit-config.yaml` suite in CI against the files changed in the PR/push
  (`pre-commit run --from-ref … --to-ref …`), rather than a separately-maintained
  CI subset. This eliminates CI↔local divergence for changed code without a
  high-risk repo-wide retro-cleanup of pre-existing debt; existing whole-repo CI
  checks are retained as additional coverage. (Refined 2026-06-29 — see Clarifications.)
- **FR-007** (P2): Secret detection MUST run in the gate of record, not only in
  local checks.
- **FR-008**: The enforcement configuration MUST be current — no deprecated
  enforcement tool MAY remain, and pinned tool versions MUST be within the
  project's currency policy.
- **FR-009**: Each language's standard MUST be documented in one authoritative
  location with an explicit enforcement-scope verdict (Active / Conditional /
  Document-only), covering at minimum Python, Bash, Go, Rust, and Terraform, plus
  the repo's other tracked languages (Markdown, YAML, JSON, bats, PowerShell).
- **FR-010**: Dormant-language checks (Go, Rust, Terraform — no real files today)
  MUST be retained as guarded, version-current scaffold references that fire only
  when matching sources appear, with deprecated tools replaced (e.g., Trivy for
  tfsec, golangci-lint v2, guarded cargo hooks) — not removed.
- **FR-011**: Standards exceptions MUST be expressible inline with a stated
  rationale; blanket file-level suppression MUST NOT be the default practice.
- **FR-012**: Enforcement MUST exclude generated/vendored/explicitly-excluded paths
  already defined by the repo.
- **FR-013**: The Python standard MUST have a single committed configuration
  surface so checks apply a consistent project profile rather than tool defaults.
- **FR-014**: Existing repo-specific shell guarantees and conventions (macOS Bash
  3.2 empty-array safety, the `err()` error convention, the `--help` convention)
  MUST be preserved and represented in the documented standard.
- **FR-015**: The four-layer enforcement model (editor → edit-time → commit-time →
  gate-of-record) MUST be retained and extended, not replaced.

### Key Entities

- **Coding Standard (per language)**: the set of rules for a language plus its
  enforcement-scope verdict (Active / Conditional / Document-only).
- **Enforcement Layer**: one of editor, edit-time, commit-time, gate-of-record —
  each with its own latency and blocking semantics.
- **Edit-time Check**: the per-edit validation behavior (advisory, non-blocking,
  non-mutating, fail-open, time-bounded).
- **Standards Document**: the single authoritative reference linked from the
  contributor and agent guides.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of in-session edits to primary-language files trigger a
  standards check that reports any violation before the edit is considered
  complete.
- **SC-002**: A standards violation introduced into a primary-language file is
  surfaced in the same session it is introduced (not deferred to commit or PR) in
  at least 95% of trials.
- **SC-003**: Edit-time validation never blocks or alters a file — across a
  representative edit set, 0 edits are blocked and 0 files are modified by the
  check.
- **SC-004**: 0 standards enforced locally for a primary language are absent from
  the gate of record (no bypass path).
- **SC-005**: 0 deprecated enforcement tools remain in the configuration.
- **SC-006**: 100% of in-scope languages have a documented standard with an
  enforcement-scope verdict.
- **SC-007**: A contributor without local hooks installed cannot merge a change
  that violates a primary-language standard — the gate fails in 100% of
  planted-violation trials.
- **SC-008**: Edit-time checking adds only a small, bounded overhead per edit so
  the editing workflow is not noticeably slowed (a slow check is abandoned rather
  than allowed to stall the session).

## Assumptions

- **Primary vs. peripheral languages**: Bash (including bats tests) and Python are
  the primary, actively-enforced languages; Markdown, YAML, and JSON are actively
  enforced structured/doc formats; Go, Rust, and Terraform have no real source in
  the repo today and are documented-only/conditional until sources land.
- **Meaning of "whenever a file is edited / modified"**: primarily the AI agent's
  in-session file operations (the existing `Write|Edit` per-edit hook mechanism)
  and human format-on-save; commit and pull-request gates remain the *blocking*
  enforcement points.
- **Edit-time enforcement is advisory (non-blocking) by default**, consistent with
  the repo's existing per-edit hooks; blocking enforcement stays at commit and PR.
- The repo's existing four-layer enforcement model and its excluded paths (e.g.,
  `.Jules/`, `node_modules/`, scaffold templates) are retained.
- This is an **improvement** to existing enforcement, not a greenfield build; a
  full research dossier (per-language standards, tooling currency, enforcement
  model) is recorded in [research-notes.md](./research-notes.md).
- The user's proposed sample `.pre-commit-config.yaml` is treated as a starting
  reference; several entries in it are outdated or unmaintained (see research
  notes) and the implemented configuration will use current, maintained equivalents.
