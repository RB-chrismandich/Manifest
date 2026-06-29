# Phase 1 Data Model — Coding Standards & Edit-Time Enforcement

This feature has no runtime database; the "entities" are configuration/data shapes
expressed in committed files. Each is defined with its fields, validation rules,
and the requirement(s) it serves.

## Entity: Coding Standard (per language)

Authored in `docs/CODING_STANDARDS.md`, one section per language.

| Field | Type | Rules |
|---|---|---|
| `language` | string | One of: Bash, Python, Markdown, YAML, JSON, bats, PowerShell, Go, Rust, Terraform |
| `rules` | list<string> | Each rule is a single testable directive (MUST/SHOULD) |
| `scopeVerdict` | enum | `Active` \| `Conditional` \| `Document-only` |
| `enforcedBy` | list<layer> | Subset of {editor, edit-time, commit, gate-of-record} |
| `tools` | list<string> | Maintained tools that enforce the rules |

**Verdict assignment** (FR-009): Bash, Python, Markdown, YAML, JSON = `Active`;
bats, PowerShell = `Active` (gap → SHOULD); Go, Terraform, Rust = `Conditional`
(guarded hooks fire only when sources appear).

## Entity: Enforcement Layer

Conceptual model captured in `docs/CODING_STANDARDS.md`; realized across config files.

| Field | Type | Rules |
|---|---|---|
| `name` | enum | `editor` \| `edit-time` \| `commit` \| `gate-of-record` |
| `latency` | string | editor 0 · edit-time <1s · commit 0.3–s · CI minutes |
| `blocks` | bool | editor=false, edit-time=**false**, commit=true, gate-of-record=true |
| `autofix` | bool | only `commit` may auto-fix; edit-time=**false** |
| `mechanism` | string | `.editorconfig` / PostToolUse hook / `.pre-commit-config.yaml` / `ci.yml` |

Invariant (FR-015): all four layers persist; edit-time is the new lint-bearing one.

## Entity: Edit-time Dispatch Entry

The dispatch table inside `lint_on_edit_hook.sh` (FR-001/002/003/004).

| Field | Type | Value examples |
|---|---|---|
| `extension` | string | `.sh`, `.py`, `.yml`/`.yaml`, `.json`, `.md`, `.mdc` |
| `linter` | command | `shellcheck`, `ruff check`, `yamllint`, `python -c json.load`, `markdownlint` |
| `args` | list | severity/format flags; **never** a fixer flag |
| `advisory` | bool | always `true` (stderr only) |
| `installed` | guard | `command -v <linter>` — absent ⇒ skip (fail-open) |
| `excluded` | guard | path under `.Jules/`, `node_modules/`, `.git/`, scaffold templates ⇒ skip |

Dispatch table (initial):

| ext | tool | invocation (advisory) |
|---|---|---|
| `.sh` | shellcheck | `shellcheck --severity=info <f>` (advisory; commit/CI use `warning`) |
| `.py` | ruff | `ruff check <f>` (no `--fix`) |
| `.yml`/`.yaml` | yamllint | `yamllint -f parsable <f>` |
| `.json` | python3 | `python3 -c 'import json,sys; json.load(open(sys.argv[1]))' <f>` |
| `.md` | markdownlint | `markdownlint -c .markdownlint.jsonc <f>` |
| `.mdc` | markdownlint | `markdownlint -c .markdownlint.jsonc <f>` |

State: the hook is stateless per invocation; exit code is **always 0**.

## Entity: pre-commit configuration

`.pre-commit-config.yaml` (commit layer + CI gate of record).

| Field | Type | Rules |
|---|---|---|
| `repos[].rev` | string | Current maintained tag (research §5) |
| `hooks[].id` | string | No deprecated id (`terraform_tfsec` removed) |
| `hooks[].files`/`types_or` | scope | Dormant-language hooks scoped so they skip on no files |
| `local hooks` | list | Existing custom checks preserved; +`pyright`, +guarded Rust |

## Entity: Python project config

`pyproject.toml` (FR-013).

| Field | Type | Rules |
|---|---|---|
| `requires-python` | string | `>=3.11` |
| `[tool.ruff].line-length` | int | 88 |
| `[tool.ruff].lint.select` | list | E,W,F,I,N,UP,B,S,A,C4,DTZ,T20,RET,SIM,TCH,PTH,RUF |
| `[tool.ruff].lint.per-file-ignores` | map | `tests/** = ["S101"]` |
| `[tool.pytest.ini_options]` | table | `--strict-markers --strict-config` |
| `[tool.coverage.report].fail_under` | int | 80 (advisory in CI) |

## Relationships

- A **Coding Standard** is `enforcedBy` one or more **Enforcement Layers**.
- An **Edit-time Dispatch Entry** realizes the `edit-time` layer for one extension.
- The **pre-commit configuration** realizes both the `commit` layer and (run by CI)
  the `gate-of-record` layer (FR-005/006) — one config, two layers.
- **Python project config** parameterizes the Python standard across all layers.
