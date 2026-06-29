# Coding Standards

> Authoritative per-language coding standards for the Manifest repo and how they
> are enforced.

**Last Updated**: 2026-06-29
**Audience**: Contributors, AI coding agents
**Spec**: [specs/366-coding-standards/spec.md](../specs/366-coding-standards/spec.md)

This document is the single source of truth for the rules each language follows
and whether those rules are actively enforced, conditionally enforced, or merely
documented in this repo. Where a rule is mechanically checked, the enforcing layer
and tool are named.

## Enforcement Layers

Standards are enforced in four complementary layers, fastest/earliest to latest:

| Layer | When it runs | Blocks? | Auto-fix? | Mechanism |
|-------|--------------|---------|-----------|-----------|
| Editor | As you type / on save | No | Per editor | `.editorconfig`, LSP |
| Edit-time | After every agent `Write`/`Edit` | **No** (advisory) | **No** | `configs/claude/scripts/lint_on_edit_hook.sh` (PostToolUse) |
| Commit | On `git commit` (if `pre-commit install` was run) | Yes | Yes | `.pre-commit-config.yaml` |
| Gate of record | On every PR/push (CI) | Yes | No | `.github/workflows/ci.yml` runs pre-commit on changed files |

The **edit-time** layer is advisory only: it lints the just-edited file and writes
findings to stderr, but never blocks the edit, never rewrites the file, and fails
open when a linter is absent. The **gate of record** runs the same
`.pre-commit-config.yaml` against the files changed in a PR/push, so standards
cannot be bypassed by skipping local hooks. It is scoped to changed files (not the
whole tree) so pre-existing debt does not block unrelated work; debt is paid down
as files are touched.

## Scope Verdicts

Each language carries one verdict:

- **Active** — real files exist; rules are enforced now.
- **Conditional** — no real files yet; a guarded hook fires only when sources appear.
- **Document-only** — rules are recorded as a reference; no active hook in this repo.

| Language | Verdict | Primary tools |
|----------|---------|---------------|
| Bash | Active | shellcheck, shfmt, custom array-expansion lint |
| Python | Active | ruff (lint + format), pyright (opt-in) |
| Markdown | Active | markdownlint |
| YAML | Active | yamllint, check-yaml |
| JSON | Active | check-json / `json.load` |
| Bats | Active (tests) | bats (run); shellcheck (edit-time advisory) |
| PowerShell | Document-only | EditorConfig (PSScriptAnalyzer if it becomes load-bearing) |
| Go | Conditional | gofumpt, golangci-lint v2 |
| Rust | Conditional | rustfmt, clippy (guarded cargo hooks) |
| Terraform | Conditional | terraform fmt/validate, tflint, Trivy |

## Languages

### Bash (Active — primary)

**Rules:**

- `set -euo pipefail` at the top of every standalone script. Sourced
  `bootstrap/lib/` files may omit `-e` with a documented rationale.
- Guard empty-array expansion for macOS Bash 3.2 + `set -u`:
  `"${arr[@]+"${arr[@]}"}"`. Enforced by `tests/lint/check_array_expansion.sh`.
- Prefer `[[ ]]` over `[ ]`; quote all expansions; use `command -v`, not `which`.
- Declare function-local variables with `local`; module constants with `readonly`.
- Route error/warning output through `err() { echo "<script-name>: $*" >&2; }`.
  `bootstrap/lib/` keeps its own `print_error()` family as the sole exception.
- Every user-facing entry-point script handles `--help` (usage ≤15 lines, exit 0).
  Detection/save-hook helpers are exempt with rationale (`git_platform.sh`,
  `version_pin_hook.sh`).
- Never `eval` or interpolate untrusted input into shell source.
- Inline `# shellcheck disable=SCxxxx` with a reason only; never blanket file-level
  disables.

**Enforcement:** shellcheck `--severity=warning` (commit + CI) and
`--severity=info` (edit-time advisory); `shfmt -i 4 -ci -sr -ln bash`; the
array-expansion lint at commit and CI.

### Python (Active — primary)

**Rules:**

- Format with ruff-format; lint with ruff. Configuration lives only in
  `pyproject.toml` (`[tool.ruff]`).
- Be explicit: `import module`, never `from module import *`.
- Use type hints on public signatures; modern syntax (`list`/`dict`/`X | None`).
- Catch specific exceptions; `raise X from err`; never a bare `except:`.
- Prefer `pathlib`, f-strings, and `logging` over `os.path`, `%`/`.format`, and
  `print()` in library code.
- Keep environments isolated (`venv`/`uv`); pin test/runtime deps.

**Enforcement:** `ruff check` + `ruff format` (commit + CI on changed files);
`ruff check` advisory at edit-time; pyright is available as an opt-in manual hook
(`pre-commit run pyright --hook-stage manual`) until typed coverage grows. The CI
gate is scoped to changed files, so the existing ruff debt in legacy modules is
fixed as those files are touched.

### Markdown (Active)

**Rules:** follow `.markdownlint.jsonc` (120-column lines, `MD033`/`MD041`/`MD060`
off, `MD024` siblings-only). Fenced code blocks declare a language.

**Enforcement:** markdownlint at commit + CI on changed `.md`. Cursor rule files
(`.mdc`) are linted **advisory at edit-time** but are not a blocking gate, because
they are generated by `generate_cursor_rules.sh` (the generator owns their format).

### YAML (Active)

**Rules:** valid YAML; follow `.yamllint` (max line 150, document-start off).

**Enforcement:** `check-yaml --unsafe` + yamllint at commit + CI; yamllint advisory
at edit-time.

### JSON (Active)

**Rules:** syntactically valid JSON; 2-space indent (`.editorconfig`).

**Enforcement:** `check-json` at commit + CI; `json.load` validation advisory at
edit-time. (JSON Schema validation of config files is a future enhancement.)

### Bats (Active — test scripts)

**Rules:** Bash rules apply. Tests live in `tests/bats/` and run in CI.

**Enforcement:** executed by bats in CI; shellcheck advisory at edit-time. A
blocking shellcheck gate for `.bats` is a future enhancement.

### PowerShell (Document-only)

**Rules:** 4-space indent (`.editorconfig`); follow PowerShell community style.

**Enforcement:** EditorConfig only today. Add PSScriptAnalyzer if the `.ps1`
scripts under `.specify/extensions/git/scripts/powershell/` become load-bearing.

### Go (Conditional)

**Rules:** `gofmt`/`gofumpt`; check every `if err != nil`; small single-method
interfaces; avoid goroutine leaks and package-level mutable state; wrap errors with
`%w`; `ctx` as the first argument; run tests with `-race`.

**Enforcement:** a `golangci-lint` (v2) hook is configured but **dormant** (no real
`.go` files); it fires only when Go sources appear.

### Rust (Conditional)

**Rules:** structure data to fit ownership/lifetimes; avoid `unwrap()` — handle
`Result`/`Option`; run `cargo clippy` with `-D warnings`; minimise and document
`unsafe` (`// SAFETY:`); use newtypes/enums to encode domain constraints.

**Enforcement:** guarded local `cargo fmt --check` / `cargo clippy` hooks that run
only when `.rs` files are staged and a `Cargo.toml` exists. The unmaintained
`doublify/pre-commit-rust` is deliberately avoided.

### Terraform (Conditional)

**Rules:** `terraform fmt`; pin provider and module versions (`required_version`,
`~>`); use typed, described variables and locals instead of magic strings; store
state remotely with locking; minimise blast radius by separating environments.

**Enforcement:** `terraform_fmt`/`terraform_validate`/`terraform_tflint` plus
**Trivy** (`terraform_trivy`) hooks are configured but **dormant** (no real `.tf`
files). The deprecated `tfsec` has been removed (merged into Trivy in 2024).

## Edit-time Advisory Hook

`configs/claude/scripts/lint_on_edit_hook.sh` runs after every `Write`/`Edit` (a
PostToolUse hook in `configs/claude/settings.local.json`). It dispatches by
extension — `.sh`→shellcheck, `.py`→ruff, `.yml`/`.yaml`→yamllint, `.json`→JSON
parse, `.md`/`.mdc`→markdownlint — and:

- never blocks the edit (always exits 0);
- never auto-fixes (no `ruff --fix`, no `shfmt -w`);
- fails open when a linter is not installed;
- is time-bounded and skips generated/vendored/scaffold paths.

## Exceptions

Suppress a rule **inline, with a stated rationale**. Blanket, file-level
disables are not the default practice — scope every suppression as narrowly as
possible and explain why. Per-language inline syntax:

| Language | Inline suppression (with reason) |
|----------|----------------------------------|
| Bash | `# shellcheck disable=SC2086 — reason` (next line) |
| Python | `x = ...  # noqa: F401 — reason` |
| YAML | `# yamllint disable-line rule:line-length` |
| Markdown / MDC | `<!-- markdownlint-disable-next-line MD013 -->` |

Dormant-language hooks (Go/Rust/Terraform) are kept (not deleted) so the repo
signals it can host those languages; they fire only when matching sources appear.

## Tooling Currency

Deprecated tools are not permitted; pinned versions are kept current via
`pre-commit autoupdate`. Notable: `tfsec` → Trivy, golangci-lint v1 → v2. See
[specs/366-coding-standards/research-notes.md](../specs/366-coding-standards/research-notes.md)
for the full currency analysis.

## Related Documents

- [.pre-commit-config.yaml](../.pre-commit-config.yaml) — commit + CI hook suite
- [.editorconfig](../.editorconfig) — editor-level formatting
- [CONTRIBUTING.md](../CONTRIBUTING.md) — development workflow
- [specs/366-coding-standards/](../specs/366-coding-standards/) — spec, plan, research
