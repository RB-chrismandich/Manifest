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
  claude/                 # → ~/.claude/  (CLAUDE.md, commands/, skills/, config/, scripts/)
  cursor/                 # → ~/.cursor/  (rules/, mcp.json + symlinks to claude/)
  gemini/                 # → ~/.gemini/  (GEMINI.md, commands/, settings.json + symlinks)
  codex/                  # → ~/.codex/   (AGENTS.md symlink + symlinks to claude/)

.claude/                  # Repo-specific only (this file + settings.local.json)
bootstrap.sh              # Deploys configs/ to ~/
bootstrap/lib/            # Modular bootstrap libraries
tests/                    # Bats + pytest test suites
docs/                     # Project documentation
```

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
| Slash commands | `configs/claude/commands/` |
| Skills | `configs/claude/skills/` |
| Scripts | `configs/claude/scripts/` |
| Config files | `configs/claude/config/` |
| Cursor rules | `configs/cursor/rules/` |
| Gemini guide | `configs/gemini/GEMINI.md` |
| Bootstrap | `bootstrap.sh` + `bootstrap/lib/` |
| Tests | `tests/bats/`, `tests/python/` |
