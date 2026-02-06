# AGENTS.md

> Repository context and guidance for AI coding agents (Cursor, Claude Code, Gemini, etc.)

**Last Updated**: 2026-02-05
**Audience**: AI assistants (Cursor Agent, Claude Code, Gemini CLI), contributors
**Purpose**: Provide AI agents with repository structure, deployment process, and testing guidelines

---

This file provides guidance to AI coding agents when working with code in this repository.
It follows the [AGENTS.md standard](https://agents.md/) for unified coding agent instructions.

## Repository Purpose

This repository manages AI agent configurations for deployment to `~/.claude/` (and mirrored
to `~/.cursor/` and `~/.gemini/`) on target machines. It contains orchestration guides,
commands/rules, skills, prompts, and scripts that enable parallel LLM agent coordination
(Cursor, Gemini CLI, Claude CLI).

## Repository Structure

```text
.claude/                             # Primary configuration (Claude Code)
├── CLAUDE.md                        # Orchestration guide (deployed to ~/.claude/)
├── commands/                        # Claude Code slash commands
├── skills/code-quality/SKILL.md     # Auto-triggered code quality skill
├── prompts/                         # Agent orchestration prompt templates
├── config/                          # YAML configuration files
├── .plans/                          # Plan management (template, archive, abandoned)
└── scripts/parallel_agent.sh        # Main parallel agent orchestration script

.cursor/                             # Cursor IDE configuration (mirrors .claude/)
├── rules/                           # Cursor rules (.mdc) adapted from commands/skills
│   ├── orchestration.mdc            # Always-on orchestration guide
│   ├── code-quality.mdc             # Auto-triggered quality/security checks
│   ├── refactor-python.mdc          # Python analysis rule
│   ├── refactor-shell.mdc           # Shell analysis rule
│   ├── docs-readme.mdc              # README improvement rule
│   ├── docs-improve.mdc             # Diataxis documentation rule
│   ├── docs-diagrams.mdc            # Mermaid diagram generation rule
│   ├── project-commit.mdc           # Commit pipeline rule
│   └── plan-manage.mdc              # Plan lifecycle rule
├── scripts -> ../.claude/scripts/   # Symlink to shared scripts
├── config -> ../.claude/config/     # Symlink to shared configs
├── prompts -> ../.claude/prompts/   # Symlink to shared prompts
└── .plans -> ../.claude/.plans/     # Symlink to shared plans

.gemini/                             # Gemini CLI configuration (mirrors .claude/)
├── GEMINI.md                        # Orchestration guide for Gemini CLI
├── commands/                        # TOML slash commands
│   ├── project-commit.toml          # Commit pipeline command
│   ├── refactor-python.toml         # Python analysis command
│   ├── refactor-shell.toml          # Shell analysis command
│   ├── docs-readme.toml             # README improvement command
│   ├── docs-improve.toml            # Diataxis documentation command
│   ├── docs-diagrams.toml           # Mermaid diagram generation command
│   ├── plan-manage.toml             # Plan lifecycle command
│   └── checkpoint.toml              # Context checkpoint command
├── settings.json                    # Gemini CLI project settings
├── skills/code-quality/SKILL.md     # Symlinked from .claude/
├── scripts -> ../.claude/scripts/   # Symlink to shared scripts
├── config -> ../.claude/config/     # Symlink to shared configs
├── prompts -> ../.claude/prompts/   # Symlink to shared prompts
└── .plans -> ../.claude/.plans/     # Symlink to shared plans

bootstrap.sh                         # macOS/Linux bootstrap script
AGENTS.md                            # This file (AI agent instructions)
CLAUDE.md                            # Claude Code-specific project instructions
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
```

### Service Toggles

```bash
--enable-claude / --disable-claude   # Claude CLI (default: enabled)
--enable-gemini / --disable-gemini   # Gemini CLI (default: enabled)
--enable-cursor / --disable-cursor   # Cursor agent (default: enabled)
```

## Manual Deployment

If not using bootstrap.sh, copy the configuration directories manually:

```bash
# Deploy Claude Code configuration
cp -r .claude/* ~/.claude/
chmod +x ~/.claude/scripts/*.sh

# Deploy Cursor configuration (optional)
mkdir -p ~/.cursor/rules
cp .cursor/rules/*.mdc ~/.cursor/rules/
# Recreate symlinks for shared assets
ln -sf ~/.claude/scripts ~/.cursor/scripts
ln -sf ~/.claude/config ~/.cursor/config
ln -sf ~/.claude/prompts ~/.cursor/prompts
ln -sf ~/.claude/.plans ~/.cursor/.plans

# Deploy Gemini configuration (optional)
mkdir -p ~/.gemini/commands ~/.gemini/skills/code-quality
cp .gemini/GEMINI.md ~/.gemini/
cp .gemini/commands/*.toml ~/.gemini/commands/
ln -sf ~/.claude/scripts ~/.gemini/scripts
ln -sf ~/.claude/config ~/.gemini/config
ln -sf ~/.claude/prompts ~/.gemini/prompts
ln -sf ~/.claude/.plans ~/.gemini/.plans
ln -sf ~/.claude/skills/code-quality/SKILL.md ~/.gemini/skills/code-quality/SKILL.md
```

Required CLI tools (install those you want to use):

- `claude` - `npm install -g @anthropic-ai/claude-code`
- `gemini` - `npm install -g @google/gemini-cli`
- `cursor` - Download from <https://cursor.sh>

## Key Files

| File | Purpose |
|------|---------|
| `.claude/CLAUDE.md` | Main orchestration guide for Claude Code |
| `.cursor/rules/orchestration.mdc` | Main orchestration guide for Cursor (always-on rule) |
| `.gemini/GEMINI.md` | Main orchestration guide for Gemini CLI |
| `.claude/scripts/parallel_agent.sh` | Bash script that runs agents in parallel with consensus scoring |
| `.claude/config/command_config.yml` | Thresholds, tool policies, model selection, error recovery |
| `.claude/config/validation_criteria.yml` | Tier 1 (critical) and Tier 2 (quality) validation rules |

## Available Commands / Rules

### Claude Code Commands

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/project-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL |
| `/refactor-python` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-shell` | Bash/Shell script security and quality analysis | ALWAYS |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL |
| `/docs-readme` | Improve README documentation | NO |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |

### Cursor Rules

| Rule | Trigger | Description |
|------|---------|-------------|
| `orchestration` | Always on | Parallel agent orchestration guide |
| `code-quality` | Globs: `**/*.py,*.js,*.ts,*.go,*.sh` | Auto-triggered security/quality checks |
| `refactor-python` | Globs: `**/*.py` | Python analysis |
| `refactor-shell` | Globs: `**/*.sh,*.bash` | Shell analysis |
| `docs-readme` | Globs: `**/README.md` | README improvement |
| `docs-improve` | Globs: `docs/**/*.md` | Diataxis documentation |
| `docs-diagrams` | Globs: `docs/**/*.md` | Mermaid diagram generation |
| `project-commit` | Manual | Commit pipeline |
| `plan-manage` | Globs: `.plans/**/*.md` | Plan lifecycle |

### Gemini CLI Commands

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/project-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL |
| `/refactor-python` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-shell` | Bash/Shell script security and quality analysis | ALWAYS |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL |
| `/docs-readme` | Improve README documentation | NO |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |
| `/checkpoint` | Context checkpoint for session continuity | NO |

## Parallel Agent Orchestration

All agents share the same orchestration script at `.claude/scripts/parallel_agent.sh`.

```bash
# Basic code review (all 3 agents)
~/.claude/scripts/parallel_agent.sh --json --timeout 600 --review /absolute/path/to/file

# Security analysis with maximum capability models
~/.claude/scripts/parallel_agent.sh --json --full-output --validate --timeout 900 \
  --cursor-model advanced --claude-model opus --analyze /absolute/path/to/file
```

### Consensus Thresholds

- `>=80%`: High confidence - auto-proceed
- `50-79%`: Medium confidence - highlight disagreements
- `<50%`: Low confidence - escalate for human review

### Validation Verdicts

- `APPROVED`: Tier 1 passes, Tier 2 score >= 0.60
- `NEEDS_REVIEW`: Tier 1 passes, Tier 2 score < 0.60
- `BLOCKED`: Any Tier 1 check fails

## Testing Changes

```bash
# Test parallel agent script
.claude/scripts/parallel_agent.sh --json "Test prompt"

# Test specific mode
.claude/scripts/parallel_agent.sh --json --review /path/to/file

# Validate YAML configs
python3 -c "import yaml; yaml.safe_load(open('.claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('.claude/config/validation_criteria.yml'))"
```

## Plan Management

Implementation plans are tracked in `.claude/.plans/` (symlinked at `.cursor/.plans/` and
`.gemini/.plans/`) as date-prefixed markdown files (`YYYYMMDD-description.md`).

Lifecycle: `CREATE -> ACTIVE -> COMPLETED (.archive/) or ABANDONED (.abandoned/)`

## Adding New Configuration

### Adding a Claude Code Command

1. Create a markdown file in `.claude/commands/` (e.g., `my-command.md`)
2. Add tool policies to `.claude/config/command_config.yml`
3. Invoke as `/my-command` in Claude Code

### Adding a Cursor Rule

1. Create an `.mdc` file in `.cursor/rules/` (e.g., `my-rule.mdc`)
2. Add YAML frontmatter with `description`, `globs`, and `alwaysApply`
3. Rule auto-attaches when files matching `globs` are referenced

### Adding a Gemini CLI Command

1. Create a `.toml` file in `.gemini/commands/` (e.g., `my-command.toml`)
2. Add `description` and `prompt` fields (TOML format)
3. Invoke as `/my-command` in Gemini CLI

---

## Related Documents

- [README.md](README.md) - Project overview and quick start
- [CLAUDE.md](CLAUDE.md) - Claude Code-specific project instructions
- [docs/README.md](docs/README.md) - Documentation hub
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) - First-time setup walkthrough
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Complete configuration reference
- [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) - Visual system documentation
- [.claude/.plans/README.md](.claude/.plans/README.md) - Plan management quick reference
