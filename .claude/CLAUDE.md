# Manifest Repository — Developer Guide

> This file provides Claude Code with context for working **inside** the Manifest
> repository. It is intentionally minimal to avoid overriding your active
> `~/.claude/` session configuration.

## What This Repo Is

Repository purpose and the full directory tree are in the root
[CLAUDE.md](../CLAUDE.md) (loaded alongside this file).

**Important**: The deployment source configs live in `configs/`, not in root
dot-directories. This prevents project-level config from overriding your active
session when working in this repo.

## Skill Management

Skills physically live in `.apm/skills/` — the **sole** source of truth.
`configs/claude/skills` is a backward-compat **symlink** to it; do not replace
it with a real directory.

- **Home deploy** (`~/.claude/skills` + Cursor/Gemini/Codex/Antigravity symlinks)
  is owned by `bootstrap.sh` (`deploy_home_skills` copies `.apm/skills/` →
  `~/.claude/skills`).
- **Local skill-dev**: `apm-dev-sync` — publish-free; removes deleted skills.
- **skillshare was removed 2026-07-27** (feature 522, FR-021a). There is no
  `.skillshare/` tree, no `.skillshare/config.yaml`, and no `skillshare`
  invocation anywhere in the repo. Do not reintroduce one: `.apm/skills` is
  authoritative and a second skill tree is a spec violation, not a convenience.
  Retired with it: the project-scoped Copilot target (`.github/skills`) and the
  `skillshare install|audit|check|update` supply-chain lifecycle. Externally
  sourced skills (Stitch, `ai-hooks-integration`) are now vendored in
  `.apm/skills` with no re-sync path until APM's published-package model is
  verified — see `specs/522-apm-deploy-migration/decision-record.md`.
- Automation must read the physical `.apm/skills/`; shell globs are
  symlink-safe, but `find`/`os.walk` over `configs/claude/skills` need
  `-L`/`followlinks`.
- **SkillClaw** (optional, opt-in via `./bootstrap.sh --enable-skillclaw`) is a *proposer*:
  it evolves skills from captured CLI-agent sessions and opens review PRs into
  `.apm/skills/` via `/skill-evolve`. It never writes the source of truth
  directly. Capture is fail-open (passive ingestion of `~/.claude/projects` JSONL; a
  failed ingest run logs and continues rather than blocking) and storage is
  `chmod 700`. See `docs/SKILLCLAW.md`.

## Common Tasks

### Deploy to your home directory

```bash
./bootstrap.sh
```

### Run tests

```bash
# Shell script tests
bats tests/bats/

# Python tests
pytest tests/python/

# Lint
shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh
yamllint configs/claude/config/*.yml
```

## Script Conventions (configs/claude/scripts/)

> Full per-language standards and enforcement layers live in
> [docs/CODING_STANDARDS.md](../docs/CODING_STANDARDS.md). The conventions below
> are the Bash-specific essentials.

- **Error output**: `err() { echo "<script-name>: $*" >&2; }` is canonical;
  route all error/warning messages through it (helpers like `error_msg()` may
  delegate to `err()`). Exempt: usage/help text, interactive prompts, blank
  separator lines, and success/info status output. `bootstrap/lib/` keeps its
  own `print_error()` family (specs/003 R7).
- **`--help`**: every user-facing entry point (`.sh` and `.py`) handles `--help`
  — usage + flags, ≤15 lines, exit 0, before any config/state lookup. Coverage
  is **enumerated, not listed** by `tests/bats/help_coverage.bats`; opt out in
  the file with `# help-coverage: exempt — <why>` under the shebang. Libraries
  and `manifest` shims are excluded automatically. Rationale:
  [docs/CODING_STANDARDS.md](../docs/CODING_STANDARDS.md#python-active--primary).

## Key Paths (in this repo)

Paths are mapped in the root [CLAUDE.md](../CLAUDE.md) structure tree. One not
listed there: `docs/SPEC-SYSTEMS.md` — spec/plan systems map (speckit vs
superpowers vs `.plans` vs `.Jules`).
