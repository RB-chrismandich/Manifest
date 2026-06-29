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

## Skill Management (skillshare)

Skills physically live in `.skillshare/skills/` (the source of truth, managed by
`skillshare`). `configs/claude/skills` is a backward-compat **symlink** to it —
do not replace it with a real directory.

- **Home deploy** (`~/.claude/skills` + Cursor/Gemini/Codex/Antigravity symlinks)
  is owned by `bootstrap.sh` (`deploy_home_skills` copies the physical
  `.skillshare/skills/` → `~/.claude/skills`). skillshare cannot expand `~`, so
  it is NOT the home deployer.
- **skillshare** owns the project-scoped Copilot target (`.github/skills`) and the
  supply-chain lifecycle: `skillshare install <repo>`, `audit`, `check`, `update`.
- `.skillshare/config.yaml` is **committed** (central infra) — edit it only when
  intentionally changing the shared setup, to avoid per-clone drift. skillshare
  may re-add ignore entries on `install`/`upgrade`; re-check `.skillshare/.gitignore`
  so committed skills (e.g. `ai-hooks-integration`) stay tracked.
- Automation must read the physical `.skillshare/skills/`; shell globs are
  symlink-safe, but `find`/`os.walk` over `configs/claude/skills` need
  `-L`/`followlinks`.
- **SkillClaw** (optional, opt-in via `./bootstrap.sh --enable-skillclaw`) is a *proposer*:
  it evolves skills from captured CLI-agent sessions and opens review PRs into
  `.skillshare/skills/` via `/skill-evolve`. It never writes the source of truth
  directly. Capture is fail-open (a dead daemon degrades to direct-to-provider) and
  storage is `chmod 700`. See `docs/SKILLCLAW.md`.

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
- **`--help`**: every user-facing entry point script handles `--help`
  (usage + flags, ≤15 lines, exit 0). Exempt with rationale (specs/003 R6):
  `version_pin_hook.sh` (save-hook wrapper, not user-invoked) and
  `git_platform.sh` (internal detection helper used by git_ops.sh).

## Key Paths (in this repo)

Paths are mapped in the root [CLAUDE.md](../CLAUDE.md) structure tree. One not
listed there: `docs/SPEC-SYSTEMS.md` — spec/plan systems map (speckit vs
superpowers vs `.plans` vs `.Jules`).
