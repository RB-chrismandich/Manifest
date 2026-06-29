# Coding-Standards Research Dossier — Manifest Repo

> Grounding research for the coding-standards feature spec (WHAT/WHY) and a later
> implementation plan. Produced by a multi-agent research workflow
> (current-state audit + per-language research + edit-time enforcement analysis +
> config-drift review). Tool/version claims were web-validated as of 2026-06-28.
> This is **pre-spec supporting evidence**; the authoritative requirements live in
> [spec.md](./spec.md).

## 1. Executive Summary

This is an **improvement of existing enforcement, not a greenfield build**.
Manifest already runs four enforcement layers — `.editorconfig`, Claude Code
PostToolUse hooks, a comprehensive `pre-commit` suite, and a narrower GitHub
Actions CI gate — so the work must refine and close gaps, not invent a regime.

Key structural insight: **the edit-time layer (PostToolUse on `Write|Edit`) is
the only layer that fires on every agent edit, yet it runs zero language
linters** — only `version_pin_hook.sh` (advisory, ~7 filename patterns) and
`spec_review.sh --silent` (async spec consistency). An entire editing session can
accrue shellcheck/ruff/yamllint violations with no in-session signal.

Second insight: **CI never invokes pre-commit**, so ruff, shfmt, gitleaks,
type-checking, and broad markdown linting are local-only and bypassable by anyone
who skips `pre-commit install`.

Scope reality: **Bash (46 `.sh` + 40 `.bats`) and Python (91 `.py`) are the
primary languages**; Go, Rust, and Terraform have zero real files (scaffold
templates only) and belong in the standard as documented-but-dormant references,
not active gates.

## 2. Current Enforcement Layers & Gaps

| Layer | Mechanism / files | What it enforces | Primary gaps |
|---|---|---|---|
| (a) Editor | `.editorconfig` | charset/LF/final-newline/trailing-ws; indent (sh=4, yml/json/md=2) | Invisible to the agent (no editor process); no verification; no `.ps1` rule |
| (b) Edit-time | `configs/claude/settings.local.json` → `version_pin_hook.sh`, `spec_review.sh --silent` | Version-pin warnings (~7 filename patterns); async spec consistency | **Runs no language linter**; only per-edit layer yet lints nothing |
| (c) Commit-time | `.pre-commit-config.yaml` (+ `.markdownlint.jsonc`, `.yamllint`, `.gitleaks.toml`) | shellcheck, shfmt, markdownlint (all `.md`), yamllint (all YAML), ruff+ruff-format, gitleaks, custom array/credential/stale-path/yaml-config hooks | Only runs if `pre-commit install` was run; bypassable; no type checking; `.mdc`/`.bats`/`.ps1` uncovered |
| (d) Push-time CI | `.github/workflows/ci.yml` | shellcheck (hard-coded globs), array-expansion lint, yamllint (`configs/claude/config/*.yml` only), markdownlint-cli2 (5 doc globs), pyyaml load, bats, pytest, structure checks | **Does not run pre-commit**; no ruff, shfmt, gitleaks, type-check; markdown scope ~13 of 303 files |

**Cross-cutting gaps (highest priority):**

- **CI ↔ pre-commit divergence**: gitleaks, ruff, shfmt, broad markdown linting exist *only* in pre-commit → bypassable.
- **Python not linted in CI**: ruff is pre-commit-only; CI runs pytest only. No type checker anywhere. No root `pyproject.toml` → ruff runs on defaults.
- **`.mdc` (90 files, `configs/cursor/rules/`) entirely unenforced** at every layer (`types: [markdown]` maps to `.md` only).
- **`.bats` (40), `.ps1` (4), `.jsonc` (1) unlinted**; JSON validated for syntax only.
- **Dead pre-commit hooks**: golangci-lint, eslint, terraform_tflint/tfsec have zero real files.
- **Hard-coded CI shellcheck globs** miss new `.sh` outside `configs/claude/scripts/` and `bootstrap/lib/`.

## 3. Refined Per-Language Standards & Scope Verdicts

Verdict legend: **Active** = enforce now · **Conditional** = dormant hook, fires
only if files appear · **Document-only** = recorded reference pattern, no active
hook in this repo.

### Bash — Active (primary; 46 `.sh` + 40 `.bats`)

1. `set -euo pipefail` at the top of every standalone script; sourced
   `bootstrap/lib/` files may omit `-e` with a documented rationale.
2. Guard empty-array expansion with the Bash 3.2 + `set -u` idiom
   `"${arr[@]+"${arr[@]}"}"` (already enforced by `tests/lint/check_array_expansion.sh`).
3. Use `[[ ]]`, never `[ ]`, in new code; quote all expansions; inline
   `# shellcheck disable=SCxxxx` with rationale only — never file-level blanket disables.
4. `local` for all function locals; `readonly` for module constants; `command -v` (not `which`).
5. Error convention `err() { echo "<script-name>: $*" >&2; }`; `bootstrap/lib/`
   keeps `print_error()` as the sole exception.
6. Every user-facing entry point handles `--help` (≤15 lines, exit 0); detection
   helpers exempt with rationale (`git_platform.sh`, `version_pin_hook.sh`).
7. Never `eval`/interpolate untrusted input into shell source.
8. Format `shfmt -ln bash -i 4 -ci`; lint `shellcheck --severity=warning`
   (commit gate), `--severity=style` advisory at edit-time.

### Python — Active (primary; 91 `.py`)

1. Format with **ruff-format** (line-length 88); no black/autopep8.
2. Lint with **ruff check** enabling E/W, F, I, N, UP, B, S, A, C4, DTZ, T20,
   RET, SIM, TCH, PTH, RUF; suppress `S101` only under `tests/**`.
3. Modernize type annotations for 3.11+ (built-in generics, `X | None`).
4. Annotate all public signatures; type-only imports under `if TYPE_CHECKING:`.
5. Catch specific exceptions only; `raise X from err`; no bare `except:`.
6. `pathlib.Path` over `os.path`; f-strings; `logging` over `print()` in library code.
7. **`pyproject.toml` is the single config surface** — none exists at repo root today.
8. `pytest --strict-markers --strict-config`; coverage `fail_under = 80`.
9. Add a **type checker** (pyright preferred; mypy if plugins required).

### Markdown / MDC — Active (.md) / unenforced gap (.mdc) (303 `.md`, 90 `.mdc`)

- `.md`: markdownlint via `.markdownlint.jsonc` on all `.md` in pre-commit; **CI scope** (~5 globs) should widen or accept pre-commit as authoritative.
- `.mdc`: decide explicitly — extend markdownlint to `configs/cursor/rules/*.mdc` or formally exclude with rationale. Today an unowned gap.

### YAML — Active (57 files)

- `check-yaml --unsafe` + yamllint on all YAML; **CI yamllint must widen** from `configs/claude/config/*.yml` to include `.github/workflows/*.yml`, `configs/cursor/*.yml`, `configs/gemini/*.yml`.

### JSON — Active (syntax) / SHOULD add schema (33 `.json` + 1 `.jsonc`)

- `check-json` (syntax, `.json` only); consider JSON Schema validation for `settings.local.json`, `mcp.json`, hint registries.

### Bats — Active gap (40 files)

- Executed in CI but **never linted**. Add shellcheck coverage for `.bats` (bats-aware) or accept as a documented gap.

### PowerShell — Document-only / SHOULD add (4 `.ps1`)

- No PSScriptAnalyzer, no EditorConfig `.ps1` rule, no CI step. At minimum add an EditorConfig rule.

### Go — Conditional / Document-only (0 real `.go`)

- Standards (gofumpt, `golangci-lint v2` with `version: "2"`, `%w` wrapping, `ctx` first arg, `-race`, govulncheck) recorded as scaffold reference. Existing `golangci-lint v1.63.4` hook is a no-op and **must be bumped to v2.x** if ever activated.

### Rust — Document-only (0 `.rs`)

- Standards (rustfmt `style_edition = "2024"`, Clippy `-D warnings`, `[lints]` in Cargo.toml, `// SAFETY:` on unsafe, cargo-deny/cargo-audit) recorded only. Any hook must be guarded — `doublify/pre-commit-rust` is unmaintained.

### Terraform — Document-only / Conditional (0 `.tf`)

- Standards (`terraform fmt`, `required_version`/provider `~>` pins, typed/described vars, remote encrypted state, `trivy config` not tfsec) recorded as scaffold reference. Existing `terraform_tfsec` hook is **deprecated**.

## 4. Layered Enforcement Model & Recommended "On Every Edit" Mechanism

| Layer | Latency | Blocks? | Role |
|---|---|---|---|
| (a) Editor | 0 (human only) | no | Passive whitespace/indent; invisible to the agent |
| (b) Edit-time hook | <200ms | **must not** | Advisory in-session signal to the agent |
| (c) pre-commit | 300ms–seconds | **yes** | Authoritative local gate; the only safe place for auto-fix |
| (d) CI | 2–5 min | yes | Highest-fidelity, unbypassable gate of record |

**Recommended edit-time mechanism (layer b):** a new
`configs/claude/scripts/lint_on_edit_hook.sh`, wired as a **third** PostToolUse
`Write|Edit` hook, modeled on `version_pin_hook.sh`:

- Parse the PostToolUse JSON payload to extract `file_path`.
- Dispatch by extension: `.sh`→`shellcheck --severity=warning`; `.py`→`ruff check`
  (**no `--fix`**); `.yml/.yaml`→`yamllint`; `.json`→`json.load`; optionally `.md`→`markdownlint`.
- Wrap each call with `timeout 8` and `command -v <linter> || exit 0` (fail-open).
- Write findings to **stderr**; **always `exit 0`** (advisory).

**Hard constraints (encode as requirements):**

- **Never auto-fix at edit-time** — it races the agent's in-context view of the file. Auto-fix belongs only at layer (c).
- **Never exit non-zero** at edit-time — Claude Code reads it as an error and may retry/stall.
- **Exclude slow linters** (golangci-lint cold-cache 10–30s, eslint 2–5s/file) — PostToolUse hooks run sequentially.
- Do **not** call `pre-commit run --files` from the hook — its ~500ms–1s bootstrap per edit is too slow; invoke linters directly.

**Close the CI/pre-commit divergence (layer d):** either have CI run
`pre-commit run --all-files` (single source of truth) or explicitly mirror the
missing gates (ruff check, gitleaks, shfmt `--diff`, widened markdownlint/yamllint
scope) into `ci.yml`. The spec must pick one as authoritative.

## 5. Tooling Currency — Stale/Deprecated → Replacement

| Current (file) | Status | Replacement / action |
|---|---|---|
| `terraform_tfsec` | **Deprecated** — merged into Trivy (2024) | `terraform_trivy` (same repo); AVD-* IDs map 1:1 |
| `golangci-lint v1.63.4` | **Major version behind** — v2 breaks `.golangci.yml` schema | v2.x; run `golangci-lint migrate` |
| `doublify/pre-commit-rust` (user proposal) | **Unmaintained** since ~2021 | local `cargo fmt --check` / `cargo clippy -- -D warnings` |
| `astral-sh/ruff-pre-commit v0.4.0` (user proposal) | ~12 series stale | current `v0.15.x` |
| `astral-sh/ruff-pre-commit v0.8.6` (repo) | ~7 months stale | current `v0.15.x` |
| `pre-commit-hooks v4.5.0` | 2 majors behind | `v6.x` (needs Python ≥3.9) |
| `shellcheck-py v0.9.0.6` | 2 minors behind | `v0.11.x` |
| `pre-commit-shfmt v3.7.0-4` | 4 minors behind | `v3.12.x`; add `-ln bash` |
| `markdownlint-cli v0.39.0` | ~10 minors behind | `v0.49.x` (v0.44 ESM/Node 18+ break) |
| `yamllint v1.35.1` | minor behind | `v1.38.x` |
| `pre-commit-terraform v1.96.3` | 5+ minors behind | `v1.101.x`+ (adds `terraform_trivy`) |
| `gitleaks v8.18.2` | behind | `v8.30.x` |

**Missing entirely (additions, not bumps):** Python type checker; `terraform_fmt`
- `terraform_validate`; `terraform_trivy`; guarded Rust hooks; `check-ast` +
`debug-statements` for fast Python pre-flight.

**Dead weight to prune or guard:** golangci-lint, eslint, terraform_tflint/tfsec
hooks have no real files — remove with a "this repo does not use X" signal, or keep
with a `files:` scope filter + comment noting they fire only when sources appear.

## 6. Candidate Requirements (mapped into spec.md)

**MUST:** R1 edit-time language linting on `Write|Edit`; R2 never auto-fix / always
exit 0; R3 fail-open + `timeout`; R4 CI covers what pre-commit covers (no bypass);
R5 root `pyproject.toml`; R6 remediate deprecated/stale hooks; R7 CI scopes cover
all tracked files of a type.

**SHOULD:** R8 Python type checker in CI; R9 `.mdc` ownership decision; R10 `.bats`
shellcheck; R11 `.ps1` EditorConfig + optional PSScriptAnalyzer; R12 guard/remove
dormant-language hooks; R13 single committed standards document with verdicts.

**Out of scope:** activating Go/Rust/Terraform *enforcement*; JSON Schema authoring;
replacing pre-commit with Lefthook/Watchman; edit-time auto-fixing; the `ty`
type checker (beta).

## 7. Open Questions (carried into spec.md as clarifications)

1. **Gate of record source of truth:** CI runs `pre-commit run --all-files`
   (zero divergence, slower) vs. a hand-maintained CI subset mirroring critical
   hooks (faster, must be policed)? → shapes FR-005/FR-006.
2. **Edit-time hook scope & UX:** which languages at launch (primary pair + YAML/JSON
   only, or also Markdown/MDC) and confirm advisory/non-blocking is intended? → FR-004.
3. **Dormant-language hooks:** keep Go/Rust/Terraform as guarded, version-current
   scaffold references, or remove them and re-add on demand? → FR-010.
