# CLAUDE.md

> Repository context and guidance for Claude Code when working with this codebase

**Last Updated**: 2026-06-12
**Audience**: AI assistants (Claude Code), contributors
**Purpose**: Provide Claude Code with repository structure, deployment process, and testing guidelines

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MCP Default Policy

Default MCP/tool routing (Context7, Sentry, Linear, Semgrep CLI, DeepWiki,
Glean, Google Dev Docs, Atlassian, Apify, OpenTofu) is defined once in the
deployed orchestration guide — see
[configs/claude/CLAUDE.md](configs/claude/CLAUDE.md) ("Default MCP/tool
routing"). Use the matching server when the task domain matches.

## Repository Purpose

This repository manages Claude Code agent configurations for deployment to `~/.claude/`
on target machines. It contains orchestration guides, commands, skills, prompts, and scripts
that enable parallel LLM agent coordination (Cursor, Gemini CLI, Claude CLI, Codex, Antigravity).

## Repository Structure

```text
configs/                             # Deployment source configs (deployed to ~/ via bootstrap.sh)
├── claude/                          # → ~/.claude/ (primary configuration)
│   ├── CLAUDE.md                    # Orchestration guide
│   ├── skills/                      # → ../../.skillshare/skills (symlink; source of truth)
│   ├── prompts/                     # Agent orchestration prompt templates
│   ├── config/                      # YAML configuration files
│   │   └── mcp_servers.yml          # Default MCP server registry (OAuth-capable)
│   ├── .plans/                      # Plan management (template, archive, abandoned)
│   ├── settings.local.json          # Default permissions and MCP server config
│   └── scripts/parallel_agent.py    # Main parallel agent orchestration script
├── cursor/                          # → ~/.cursor/ (Cursor IDE configuration)
│   ├── rules/                       # Cursor rules (.mdc) adapted from commands/skills
│   ├── mcp.json                     # Cursor MCP server defaults
│   └── (symlinks to ../claude/)     # scripts, config, prompts, .plans (skills via rules/)
├── gemini/                          # → ~/.gemini/ (Gemini CLI configuration)
│   ├── GEMINI.md                    # Orchestration guide for Gemini
│   ├── settings.json                # Gemini settings (includes MCP server defaults)
│   └── (symlinks to ../claude/)     # scripts, config, prompts, .plans
├── codex/                           # → ~/.codex/ (Codex CLI configuration)
│   ├── AGENTS.md -> ../../AGENTS.md # Codex guide
│   └── (symlinks to ../claude/)     # scripts, config, prompts, .plans
└── antigravity/                     # → ~/.antigravity/ (Antigravity IDE)
    └── (symlinks to ../claude/)     # scripts, config, prompts, skills, .plans

.claude/                             # Repo-specific config only (does NOT override active sessions)
├── CLAUDE.md                        # Developer guide for working in this repo
└── settings.local.json              # Repo-relevant permissions only (no MCP servers)

bootstrap.sh                         # macOS/Linux bootstrap script
bootstrap/                           # Modular bootstrap libraries + hookable modules
├── lib/                             # Shared bootstrap logic split by concern
│   ├── common.sh                    # Shared output/prompts/symlink helpers
│   ├── modules.sh                   # Hook registry + module loader
│   ├── platform.sh                  # Platform detection + timeout/browser helpers
│   ├── config.sh                    # Argument parsing + services config helpers
│   ├── install.sh                   # CLI install routines
│   ├── auth.sh                      # Authentication + state setup routines
│   ├── deploy.sh                    # Deploy/verify/summary routines
│   └── mcp.sh                       # MCP configuration/install routines
└── modules/README.md                # How to add custom bootstrap extensions
AGENTS.md                            # AI agent instructions (Cursor, Claude, Gemini, Codex, Antigravity)
```

## Bootstrap (macOS / Linux)

The `bootstrap.sh` script automates installation, deployment, and authentication.

**Supported platforms:**

- macOS (Intel and Apple Silicon)
- Linux (Debian/Ubuntu, RHEL/Fedora, Arch, openSUSE)

### Quick Start

```bash
# Full setup with all services
./bootstrap.sh

# Setup with specific services disabled
./bootstrap.sh --disable-cursor
./bootstrap.sh --disable-gemini --disable-cursor

# Skip interactive prompts
./bootstrap.sh --skip-auth --force

# Configure MCP servers (interactive per-server selection)
./bootstrap.sh --install-mcp
```

Service toggles (`--enable-*/--disable-*` for claude, gemini, cursor, codex,
antigravity, skillclaw, browser-use, gh, glab), other flags (`--skip-install`,
`--skip-auth`, `--force`, `--reconfigure`, `--install-mcp`), and the full step
list are documented in [README.md](README.md) and `./bootstrap.sh --help`.

The script installs Homebrew/Node.js and enabled CLIs as needed, deploys
`configs/` to `~/`, writes toggles to `~/.claude/config/services.yml`, and
checks authentication.

## Manual Deployment

Per-platform manual copy/symlink steps (Claude, Cursor, Gemini, Codex,
Antigravity) and required CLI installs are in
[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

## Key Files

| File | Purpose |
|------|---------|
| `configs/claude/CLAUDE.md` | Main orchestration guide - defines how Claude leverages parallel agents |
| `configs/cursor/rules/orchestration.mdc` | Main orchestration guide for Cursor (always-on rule) |
| `configs/gemini/GEMINI.md` | Main orchestration guide for Gemini CLI |
| `configs/codex/AGENTS.md` | Main orchestration guide for Codex CLI |
| `configs/claude/scripts/parallel_agent.py` | Python script that runs agents in parallel with consensus scoring |
| `configs/claude/scripts/git_platform.sh` | Platform detection script (github, gitlab, git) |
| `configs/claude/scripts/git_ops.sh` | Platform-agnostic Git operations wrapper (issue/PR management) |
| `configs/claude/scripts/linear_ops.sh` | Linear API wrapper for issue management (GraphQL) |
| `configs/claude/config/command_config.yml` | Thresholds, tool policies, model selection, error recovery |
| `configs/claude/config/linear_triage.yml` | Linear triage scoring, duplicate detection, staleness thresholds |
| `configs/claude/config/validation_criteria.yml` | Tier 1 (critical) and Tier 2 (quality) validation rules |
| `configs/claude/config/labels.yml` | Canonical label registry for GitHub, GitLab, and Linear |
| `configs/claude/scripts/label_sync.sh` | Label sync script — reads registry, provisions labels across platforms |
| `AGENTS.md` | AI agent instructions for all platforms (Cursor, Claude, Gemini, Codex) |

## Available Commands

Skills (70+, invoked as `/skill-name`) live in `.skillshare/skills/` — each
directory's `SKILL.md` frontmatter is the authoritative name and description,
and Claude Code auto-loads every description at session start, so no table is
duplicated here. Per-skill parallel-agent policy lives in
`configs/claude/config/command_config.yml` under `tool_policies`. See
[docs/COMMANDS.md](docs/COMMANDS.md) for the human-readable command reference.

**CLI tool** (installed to `~/.local/bin/`): `sync-skills` — sync
`.skillshare/skills/` to all home targets (daily skill dev workflow).

## Testing Changes

Test the parallel agent script locally:

```bash
# Test with all agents
configs/claude/scripts/parallel_agent.py --json "Test prompt"

# Test specific mode
configs/claude/scripts/parallel_agent.py --json --review /path/to/file

# Test with single agent
configs/claude/scripts/parallel_agent.py --cursor-only "Test prompt"
```

Validate YAML configuration syntax:

```bash
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/validation_criteria.yml'))"
```

## Label Management

Issue labels are managed centrally in `configs/claude/config/labels.yml` and synced across
GitHub, GitLab, and Linear via `label_sync.sh`.

**Labels**: `planned` (blue), `in-progress` (yellow), `needs-review` (orange), `done` (green),
`follow-up` (lavender), `future` (green)

```bash
# Sync all labels to the current platform
configs/claude/scripts/label_sync.sh

# Dry-run to preview changes
configs/claude/scripts/label_sync.sh --dry-run

# Sync via git_ops.sh wrapper
configs/claude/scripts/git_ops.sh label-sync
```

See [docs/COMMANDS.md](docs/COMMANDS.md#label-management) for full label reference.

## Adding New Skills

1. Create a skill directory in `.skillshare/skills/` (the source of truth) with a
   `SKILL.md` — e.g. `.skillshare/skills/my-skill/SKILL.md` — containing `name` and
   `description` frontmatter. (`configs/claude/skills/` is a compat symlink to it.)
2. Add tool policies to `configs/claude/config/command_config.yml` under `tool_policies`
3. If needed, add validation overrides to `configs/claude/config/validation_criteria.yml`

Skills are invoked as `/my-skill` in Claude Code.

## Plan Management

Implementation plans are tracked in `configs/claude/.plans/` as date-prefixed markdown files
(`YYYYMMDD-description.md`). Plans follow a lifecycle:
CREATE -> ACTIVE -> COMPLETED (`.archive/`) or ABANDONED (`.abandoned/`).
See `configs/claude/.plans/README.md` for naming conventions and rules.
Use `/plan-manage` to create plans (with parallel agent orchestration for cross-verified
approaches), review stale plans, or archive/abandon completed work.

## Configuration Reference

**Consensus thresholds** (in `command_config.yml`):

- `>=80%`: High confidence - auto-proceed
- `50-79%`: Medium confidence - highlight disagreements
- `<50%`: Low confidence - escalate for human review

**Validation tiers** (in `validation_criteria.yml`):

- Tier 1 (blocking): Security, error handling, breaking changes, cross-verification
- Tier 2 (advisory): Bug detection, performance, maintainability, test coverage

**Verdicts**:

- `APPROVED`: Tier 1 passes, Tier 2 score >= 0.60
- `NEEDS_REVIEW`: Tier 1 passes, Tier 2 score < 0.60
- `BLOCKED`: Any Tier 1 check fails

---

## Related Documents

- [README.md](README.md) - Project overview and quick start
- [docs/README.md](docs/README.md) - Documentation hub
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) - First-time setup walkthrough
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Complete configuration reference
- [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) - Visual system documentation
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - Common problems and solutions
- [configs/claude/.plans/README.md](configs/claude/.plans/README.md) - Plan management quick reference
- [configs/claude/CLAUDE.md](configs/claude/CLAUDE.md) - Orchestration guide (deployed to ~/.claude/)

<!-- SPECKIT START -->
## Active Spec Kit Feature

- `005-issue-linking-hooks` — plan: [specs/005-issue-linking-hooks/plan.md](specs/005-issue-linking-hooks/plan.md)
<!-- SPECKIT END -->

