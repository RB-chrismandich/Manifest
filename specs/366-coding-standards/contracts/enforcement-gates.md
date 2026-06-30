# Contract — Enforcement Gates (commit + gate-of-record)

Defines what the blocking layers enforce after this feature. Serves FR-005/006/007/008.

## Commit layer — `.pre-commit-config.yaml`

Runs on `git commit` when `pre-commit install` has been run. Blocking; the only
layer permitted to auto-fix.

**Changes vs. today:**

| Action | Detail |
|---|---|
| Bump revs | pre-commit-hooks `v6.x`, shellcheck-py `v0.11.x`, shfmt `v3.12.x` (+`-ln bash`), markdownlint-cli `v0.49.x`, yamllint `v1.38.x`, ruff `v0.15.x`, gitleaks `v8.30.x`, pre-commit-terraform `v1.101.x` |
| Remove deprecated | delete `terraform_tfsec` |
| Add (dormant, scoped) | `terraform_trivy`, `terraform_fmt`, `terraform_validate` (types_or `[terraform]`); golangci-lint `v2.x` (types_or `[go]`); guarded local Rust hook (cargo fmt/clippy, gated on `Cargo.toml`) |
| Add (Python) | local `pyright` hook; `check-ast`, `debug-statements` from pre-commit-hooks |
| Widen coverage | markdownlint also lints `configs/cursor/rules/*.mdc` (files: glob) |
| Preserve | all existing custom local hooks (array-expansion, credentials, stale-paths, yaml-configs, validate-bootstrap) and global `exclude` |

**Invariant**: every dormant-language hook is file-scoped so a normal commit with
no matching files skips it (no spurious runs, no env install).

## Gate of record — `.github/workflows/ci.yml`

Runs on push to `main` and all PRs. Blocking; **authoritative, unbypassable**.

**Contract (FR-005/006/007) — changed-files model (refined 2026-06-29):**

1. The `lint` job MUST run the repo's `.pre-commit-config.yaml` in CI against the
   files **changed in the PR/push**, with a cache for `~/.cache/pre-commit`:
   - pull_request: `pre-commit run --from-ref origin/$GITHUB_BASE_REF --to-ref HEAD --show-diff-on-failure`
   - push: `pre-commit run --from-ref <parent> --to-ref HEAD --show-diff-on-failure`
     (fall back to the commit's `git diff` file list when no usable parent).
2. Therefore every standard the local commit hook enforces (ruff, ruff-format,
   shfmt, shellcheck, yamllint, markdownlint, gitleaks, custom hooks) is enforced
   in CI **for new/changed code** — no bypass by skipping local install.
3. Secret detection (gitleaks) runs in CI on changed files (satisfies FR-007).
4. Existing whole-repo CI checks are **retained** as additional coverage (scoped
   shellcheck on `configs/claude/scripts` + `bootstrap`, array-expansion lint,
   yamllint on config glob, markdownlint on key docs) plus the non-pre-commit
   checks (`generate_commands_doc.py --check`, symlink integrity, case-collision,
   skill/script counts, `generate_cursor_rules.sh` regen).
5. The `test` job (bats + pytest, ≥100 tests) is unchanged and still gates merge.

**Rationale for changed-files (not `--all-files`)**: CI never ran ruff/shfmt/most
hooks before, so the repo carries pre-existing debt (39+ ruff errors, unmeasured
shfmt/markdown). `--all-files` would block on legacy debt; changed-files closes the
bypass for all new/modified code (SC-007's intent) without a high-risk mass
rewrite. Debt is paid down opportunistically as files are touched.

**Acceptance (maps to spec):**

| Spec | Gate behavior |
|---|---|
| US2 AS1 | PR that **changes** a `.py` with a ruff violation fails the `lint` job |
| US2 AS2 | PR adding a secret fails (gitleaks on changed files) |
| US2 AS3 | Audit: `lint` job runs the same `.pre-commit-config.yaml` as local, scoped to changed files |
| SC-004 | 0 primary-language standards exist only locally for changed code |
| SC-007 | Contributor without local hooks cannot merge a change that violates a standard |

## Non-goals (this contract)

- Activating Go/Rust/Terraform enforcement (no real files; hooks stay dormant).
- JSON Schema validation of `.json` (syntax check only for v1).
- Replacing pre-commit with another runner.
