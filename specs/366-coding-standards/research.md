# Phase 0 Research — Coding Standards & Edit-Time Enforcement

Decision record for the plan. Depth and citations live in
[research-notes.md](./research-notes.md) (multi-agent dossier). All spec
`[NEEDS CLARIFICATION]` markers were resolved during `/speckit-clarify`.

## D1 — Edit-time enforcement mechanism

- **Decision**: Add a third PostToolUse `Write|Edit` hook,
  `configs/claude/scripts/lint_on_edit_hook.sh`, modeled on `version_pin_hook.sh`.
  It reads the PostToolUse JSON payload, extracts `file_path`, dispatches by
  extension to a fast linter, writes findings to stderr, and **always exits 0**.
- **Rationale**: The PostToolUse layer is the only one that fires on every agent
  edit, yet today it runs no language linter. A standalone advisory script reuses
  a proven, in-repo pattern and keeps the agent loop unblocked.
- **Alternatives considered**: (a) `pre-commit run --files <f>` per edit —
  rejected: ~0.5–1s Python bootstrap per edit is too slow. (b) Editor LSP /
  format-on-save — rejected: invisible to the agent (no editor process).
  (c) File-watcher daemon (watchman/lefthook) — rejected: extra moving part,
  analyzed and dropped in the dossier.

## D2 — Edit-time scope & UX  *(resolves FR-004)*

- **Decision**: Lint `.sh`, `.py`, `.yml`/`.yaml`, `.json`, `.md`, and `.mdc`;
  advisory and non-blocking (clarify Q1 = widest set).
- **Rationale**: Covers the primary code languages plus structured config and the
  otherwise-unenforced `.mdc` rule files, at the moment of authorship.
  markdownlint-cli lints any explicitly-passed file regardless of extension, so
  `.mdc` works without renaming.
- **Alternatives**: primary-pair-only or +Markdown-only — rejected by the user in
  favor of the widest practical set.

## D3 — No-auto-fix / always-exit-0 / fail-open  *(FR-002, FR-003)*

- **Decision**: The hook never runs a fixer (`ruff --fix`, `shfmt -w`), never
  exits non-zero, skips a linter that isn't installed (`command -v … || continue`),
  and time-bounds each linter.
- **Rationale**: Auto-fix at edit time races the agent's in-context view of the
  file (stale read / silent overwrite). A non-zero exit is read by Claude Code as
  a tool error and can stall/retry. Blocking + fixing belong at the commit gate.
- **Timeout portability note**: this macOS has neither `timeout` nor `gtimeout`.
  The hook uses a `_run` wrapper: `timeout`→`gtimeout`→ a bash background+watchdog
  fallback → (last resort) run directly. Linters are fast, so the no-timeout path
  is acceptable and still exits 0.

## D4 — Gate of record  *(resolves FR-006)*

- **Decision**: The CI `lint` job runs `pre-commit run --all-files
  --show-diff-on-failure` as the authoritative gate, with a cache for
  `~/.cache/pre-commit`. Non-hook CI checks (doc-currency `generate_commands_doc.py
  --check`, symlink integrity, skill/script counts, cursor-rule regen) remain as
  separate steps (clarify Q2 = run full pre-commit).
- **Rationale**: One config = zero CI↔local divergence; ruff/shfmt/gitleaks/broad
  markdownlint can no longer be bypassed by skipping `pre-commit install`. Dormant
  hooks (Go/Rust/Terraform) have no matching files, so pre-commit **skips them
  without installing** their environments — no CI cost.
- **Alternatives**: maintained CI subset (rejected: perpetual divergence to
  police); hybrid changed-files-only (rejected: two mechanisms, weaker guarantee).
- **Refinement (2026-06-29)**: implementation revealed CI never ran ruff/most
  hooks, so `--all-files` would fail on pre-existing debt (39+ ruff errors,
  unmeasured shfmt/markdown). Revised to run pre-commit against **changed files**
  (`--from-ref/--to-ref`), keeping existing whole-repo CI checks as added coverage.
  Closes the bypass for new/changed code (SC-007) without a high-risk mass
  rewrite; debt is paid down opportunistically. See spec Clarifications 2026-06-29.

## D5 — Dormant-language hooks  *(resolves FR-010)*

- **Decision**: Keep Go/Rust/Terraform hooks as **guarded, version-current
  scaffold references** that fire only when matching sources appear (clarify Q3).
  Concretely: `terraform_tfsec`→`terraform_trivy` + add `terraform_fmt` /
  `terraform_validate`; `golangci-lint` v1.63.4→v2.x; add a guarded local Rust
  hook (`cargo fmt --check` / `cargo clippy -D warnings`) gated on `Cargo.toml`
  (avoid the unmaintained `doublify/pre-commit-rust`).
- **Rationale**: Signals "this repo can host these languages" and keeps the
  scaffold templates honest, at zero per-commit cost (file-scoped → skipped).
- **Alternatives**: remove entirely (rejected by user); document-only (rejected).

## D6 — Tooling currency  *(FR-008)*

- **Decision**: Apply the version bumps from research-notes §5 (ruff →`v0.15.x`,
  pre-commit-hooks →`v6.x`, shellcheck-py →`v0.11.x`, shfmt →`v3.12.x` +`-ln bash`,
  markdownlint-cli →`v0.49.x`, yamllint →`v1.38.x`, pre-commit-terraform
  →`v1.101.x`, gitleaks →`v8.30.x`) and remove the deprecated `terraform_tfsec`.
- **Rationale**: Stale/deprecated tools produce stale or no results. Pins are
  updated to current maintained releases as of 2026-06-28.
- **Alternatives**: leave as-is (rejected — FR-008 forbids deprecated tools).

## D7 — Python configuration surface  *(FR-013)*

- **Decision**: Add a root `pyproject.toml` with `[tool.ruff]` (rule groups
  E/W,F,I,N,UP,B,S,A,C4,DTZ,T20,RET,SIM,TCH,PTH,RUF; `S101` ignored under
  `tests/**`), `requires-python = ">=3.11"`, line-length 88, and
  `[tool.pytest.ini_options]` / `[tool.coverage]`. Add **pyright** as a local
  pre-commit hook (type-check; SHOULD, FR-008 family).
- **Rationale**: Today ruff runs on defaults with no project profile. One config
  surface makes edit-time, commit, and CI agree on the same rules.
- **Alternatives**: mypy (rejected for now — no plugin needs; pyright is faster
  here); `ty` (rejected — beta, ~53% conformance).

## D8 — Standards documentation  *(FR-009)*

- **Decision**: One `docs/CODING_STANDARDS.md` listing each language's rules and an
  **Active / Conditional / Document-only** verdict (Bash, Python, Markdown, YAML,
  JSON = Active; bats, PowerShell = Active-gap/SHOULD; Go, Terraform = Conditional;
  Rust = Document-only). Link it from `CLAUDE.md`, `.claude/CLAUDE.md`,
  `CONTRIBUTING.md`, `AGENTS.md`.
- **Rationale**: Standards are scattered today; a single source with explicit
  scope prevents "why is there a Rust rule with no Rust?" confusion.
- **Alternatives**: keep scattered (rejected — FR-009).

## D9 — Preserve repo-specific guarantees  *(FR-014)*

- **Decision**: The standards doc and configs retain the macOS Bash 3.2 empty-array
  rule (`check_array_expansion.sh`), the `err()` error convention, and the `--help`
  convention (with their documented exemptions).
- **Rationale**: These are hard-won existing guarantees (specs/003); the new doc
  must reflect, not regress, them.
