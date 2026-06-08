# Manifest Repository — Developer Guide

> This file provides Claude Code with context for working **inside** the Manifest
> repository. It is intentionally minimal to avoid overriding your active
> `~/.claude/` session configuration.

## What This Repo Is

This repository manages AI agent configurations (Claude Code, Cursor, Gemini CLI,
Codex CLI) for deployment to `~/` on target machines. It contains orchestration
guides, commands, skills, prompts, and scripts that enable parallel LLM agent
coordination.

**Important**: The deployment source configs live in `configs/`, not in root
dot-directories. This prevents project-level config from overriding your active
session when working in this repo.

## Repository Layout

```text
configs/                  # Deployment source configs (deployed to ~/ via bootstrap.sh)
  claude/                 # → ~/.claude/  (CLAUDE.md, skills/, config/, scripts/)
  cursor/                 # → ~/.cursor/  (rules/, mcp.json + symlinks to claude/)
  gemini/                 # → ~/.gemini/  (GEMINI.md, settings.json + symlinks to claude/)
  codex/                  # → ~/.codex/   (AGENTS.md symlink + symlinks to claude/)

.claude/                  # Repo-specific only (this file + settings.local.json)
bootstrap.sh              # Deploys configs/ to ~/
bootstrap/lib/            # Modular bootstrap libraries
tests/                    # Bats + pytest test suites
docs/                     # Project documentation
```

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

### Validate YAML configs

```bash
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
```

## Key Paths (in this repo)

| What | Path |
|------|------|
| Orchestration guide | `configs/claude/CLAUDE.md` |
| Skills (slash commands) | `configs/claude/skills/` |
| Scripts | `configs/claude/scripts/` |
| Config files | `configs/claude/config/` |
| Cursor rules | `configs/cursor/rules/` |
| Gemini guide | `configs/gemini/GEMINI.md` |
| Bootstrap | `bootstrap.sh` + `bootstrap/lib/` |
| Tests | `tests/bats/`, `tests/python/` |
