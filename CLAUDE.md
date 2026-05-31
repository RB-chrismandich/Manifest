# CLAUDE.md

> Repository context and guidance for Claude Code when working with this codebase

**Last Updated**: 2026-02-11
**Audience**: AI assistants (Claude Code), contributors
**Purpose**: Provide Claude Code with repository structure, deployment process, and testing guidelines

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MCP Default Policy

Use these MCP servers by default when their domain context matches the task:

- **Context7 MCP**: library/API documentation, code generation, setup steps,
  and configuration guidance.
- **Sentry MCP**: production/runtime error investigation, stack traces, issue
  triage, and release regression analysis.
- **Linear MCP**: issue requirements, acceptance criteria, project context, and
  implementation planning.
- **Semgrep CLI**: local SAST scanning, vulnerability detection, supply-chain
  and secrets checks during code review and refactoring (`semgrep scan`).
- **DeepWiki MCP**: understanding unfamiliar repositories, dependency internals,
  and upstream API contracts.
- **Glean MCP**: internal team knowledge, runbooks, ADRs, and company-specific
  documentation.
- **Google Dev Docs MCP**: official Google platform documentation (Firebase,
  Cloud, Android, Maps) when working with Google services.
- **Atlassian MCP**: Jira issues, Confluence pages, and Compass components when
  the project uses Atlassian tools.
- **Apify MCP**: web scraping, data extraction, and crawling tasks that require
  fetching structured data from external websites.
- **OpenTofu MCP**: OpenTofu/Terraform registry lookups, provider and module
  documentation, resource and datasource reference for Infrastructure as Code.

## Repository Purpose

This repository manages Claude Code agent configurations for deployment to `~/.claude/`
on target machines. It contains orchestration guides, commands, skills, prompts, and scripts
that enable parallel LLM agent coordination (Cursor, Gemini CLI, Claude CLI).

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
│   └── (symlinks to ../claude/)     # scripts, config, prompts, skills, .plans
├── gemini/                          # → ~/.gemini/ (Gemini CLI configuration)
│   ├── GEMINI.md                    # Orchestration guide for Gemini
│   ├── settings.json                # Gemini settings (includes MCP server defaults)
│   └── (symlinks to ../claude/)     # scripts, config, prompts, skills, .plans
└── codex/                           # → ~/.codex/ (Codex CLI configuration)
    ├── AGENTS.md -> ../../AGENTS.md # Codex guide
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
AGENTS.md                            # AI agent instructions (Cursor, Claude, Gemini, Codex)
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

### Service Toggles

```bash
--enable-claude / --disable-claude   # Claude CLI (default: enabled)
--enable-gemini / --disable-gemini   # Gemini CLI (default: enabled)
--enable-cursor / --disable-cursor   # Cursor agent (default: enabled)
--enable-codex / --disable-codex     # Codex CLI (default: enabled)
--enable-gh / --disable-gh           # GitHub CLI (default: auto-detect)
--enable-glab / --disable-glab       # GitLab CLI (default: auto-detect)
--install-mcp                        # Configure MCP servers (interactive per-server selection)
```

### Other Options

```bash
--skip-install    # Skip CLI tool installation
--skip-auth       # Skip authentication checks
--force           # Overwrite existing ~/.claude without prompting
--reconfigure     # Only update service toggles
```

### Reconfigure Services

```bash
# Change which services are enabled after initial setup
./bootstrap.sh --reconfigure --disable-cursor
./bootstrap.sh --reconfigure --enable-gemini --disable-claude
```

The bootstrap script:

1. Checks for and installs Homebrew (if needed)
2. Installs Node.js (required for npm-based CLIs)
3. Installs enabled CLI tools (Claude, Gemini)
4. Opens Cursor download page (if enabled)
5. Deploys configuration files from `configs/` to `~/.claude/`
6. Writes service toggles to `~/.claude/config/services.yml`
7. Checks authentication status and provides setup instructions for unauthenticated services

## Manual Deployment

If not using bootstrap.sh, copy the configuration directories manually:

```bash
# Deploy Claude Code configuration
cp -r configs/claude/* ~/.claude/
cp -r configs/claude/.[!.]* ~/.claude/ 2>/dev/null || true
chmod +x ~/.claude/scripts/*.sh ~/.claude/scripts/parallel_agent.py

# Deploy Cursor configuration (optional)
mkdir -p ~/.cursor/rules
cp configs/cursor/rules/*.mdc ~/.cursor/rules/
cp configs/cursor/mcp.json ~/.cursor/mcp.json
ln -sf ~/.claude/scripts ~/.cursor/scripts
ln -sf ~/.claude/config ~/.cursor/config
ln -sf ~/.claude/prompts ~/.cursor/prompts
ln -sf ~/.claude/.plans ~/.cursor/.plans
ln -sf ~/.claude/skills ~/.cursor/skills

# Deploy Gemini configuration (optional)
mkdir -p ~/.gemini
cp configs/gemini/GEMINI.md ~/.gemini/
cp configs/gemini/settings.json ~/.gemini/settings.json
ln -sf ~/.claude/scripts ~/.gemini/scripts
ln -sf ~/.claude/config ~/.gemini/config
ln -sf ~/.claude/prompts ~/.gemini/prompts
ln -sf ~/.claude/.plans ~/.gemini/.plans
ln -sf ~/.claude/skills ~/.gemini/skills

# Deploy Codex configuration (optional)
cp AGENTS.md ~/.codex/AGENTS.md
ln -sf ~/.claude/scripts ~/.codex/scripts
ln -sf ~/.claude/config ~/.codex/config
ln -sf ~/.claude/prompts ~/.codex/prompts
ln -sf ~/.claude/.plans ~/.codex/.plans
ln -sf ~/.claude/skills ~/.codex/skills
```

Required CLI tools (install those you want to use):

- `claude` - `npm install -g @anthropic-ai/claude-code`
- `gemini` - `npm install -g @google/gemini-cli`
- `cursor` - Download from <https://cursor.sh>
- `codex` - `npm install -g @openai/codex`

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

The following slash commands are available in Claude Code:

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/project-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL (Phase 3) |
| `/refactor-python` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-shell` | Bash/Shell script security and quality analysis | ALWAYS |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/docs-readme` | Improve README documentation | NO |
| `/issue-prioritize` | Fetch and rank open issues by impact/urgency/readiness/risk (GitHub/GitLab/Linear) | CONDITIONAL (top candidates) |
| `/issue-triage` | Linear issue audit: duplicates, staleness, priority validation | CONDITIONAL (scenario-based) |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration for create/review | CONDITIONAL |
| `/browser-test` | AI-powered E2E browser testing via browser-use YAML test prompts | CONDITIONAL |
| `sync-skills` | Sync .skillshare/skills/ to all home targets (daily skill dev workflow) | NO |

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
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
