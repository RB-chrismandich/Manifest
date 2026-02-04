# CLAUDE.md

> Repository context and guidance for Claude Code when working with this codebase

**Last Updated**: 2026-01-27
**Audience**: AI assistants (Claude Code), contributors
**Purpose**: Provide Claude Code with repository structure, deployment process, and testing guidelines

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository manages Claude Code agent configurations for deployment to `~/.claude/` on target machines. It contains orchestration guides, commands, skills, prompts, and scripts that enable parallel LLM agent coordination (Cursor, Gemini CLI, Claude CLI).

## Repository Structure

```
.claude/
├── CLAUDE.md                    # Orchestration guide (deployed to ~/.claude/)
├── commands/                    # User-invokable slash commands
├── skills/code-quality/         # Auto-triggered code quality skill
├── prompts/                     # Agent orchestration prompt templates
├── config/                      # YAML configuration files
└── scripts/parallel_agent.sh    # Main parallel agent orchestration script
bootstrap.sh                     # macOS bootstrap script
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

### Other Options
```bash
--skip-install    # Skip CLI tool installation
--skip-auth       # Skip authentication setup
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
5. Deploys configuration files to `~/.claude/`
6. Writes service toggles to `~/.claude/config/services.yml`
7. Walks through authentication for each enabled service

## Manual Deployment

If not using bootstrap.sh, copy the `.claude/` directory manually:
```bash
cp -r .claude/* ~/.claude/
chmod +x ~/.claude/scripts/*.sh
```

Required CLI tools (install those you want to use):
- `claude` - `npm install -g @anthropic-ai/claude-code`
- `gemini` - `npm install -g @google/gemini-cli`
- `cursor` - Download from https://cursor.sh

## Key Files

| File | Purpose |
|------|---------|
| `.claude/CLAUDE.md` | Main orchestration guide - defines how Claude leverages parallel agents |
| `.claude/scripts/parallel_agent.sh` | Bash script that runs agents in parallel with consensus scoring |
| `.claude/config/command_config.yml` | Thresholds, tool policies, model selection, error recovery |
| `.claude/config/validation_criteria.yml` | Tier 1 (critical) and Tier 2 (quality) validation rules |

## Available Commands

The following slash commands are available in Claude Code:

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/refactor` | Python codebase security and quality analysis | ALWAYS |
| `/shell-refactor` | Bash/Shell script security and quality analysis | ALWAYS |
| `/generate-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/improve-docs` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/improve-readme` | Improve README documentation | NO |

## Testing Changes

Test the parallel agent script locally:
```bash
# Test with all agents
.claude/scripts/parallel_agent.sh --json "Test prompt"

# Test specific mode
.claude/scripts/parallel_agent.sh --json --review /path/to/file

# Test with single agent
.claude/scripts/parallel_agent.sh --cursor-only "Test prompt"
```

Validate YAML configuration syntax:
```bash
python3 -c "import yaml; yaml.safe_load(open('.claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('.claude/config/validation_criteria.yml'))"
```

## Adding New Commands

1. Create a markdown file in `.claude/commands/` (e.g., `my-command.md`)
2. Add tool policies to `.claude/config/command_config.yml` under `tool_policies`
3. If needed, add validation overrides to `.claude/config/validation_criteria.yml`

Commands are invoked as `/my-command` in Claude Code.

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
- [.claude/CLAUDE.md](.claude/CLAUDE.md) - Orchestration guide (deployed to ~/.claude/)
