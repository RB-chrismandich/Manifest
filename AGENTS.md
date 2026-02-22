# Manifest

> Repository context and guidance for AI coding agents (Cursor, Claude Code,
> Gemini, Codex, etc.)

**Audience**: AI assistants (Cursor Agent, Claude Code, Gemini CLI, Codex CLI),
contributors
**Purpose**: Provide AI agents with repository structure, deployment process,
and testing guidelines

This file provides guidance to AI coding agents when working with code in this
repository. It follows the [AGENTS.md standard](https://agents.md/) for unified
coding agent instructions.

## Repository Overview

Manifest is a **Parallel Agent Orchestration Framework** that enables multiple
AI models (Cursor, Claude 3.7 Sonnet, Gemini 2.0 Flash, OpenAI o3-mini) to work
together on coding tasks. It provides a unified configuration layer that deploys
consistent skills, prompts, and settings across different AI tools.

### Core Architecture

This repository manages AI agent configurations for deployment to `~/.claude/`
(and mirrored to `~/.cursor/`, `~/.gemini/`, and `~/.codex/`) on target
machines. It contains orchestration guides, skills, prompts, and scripts that
enable a multi-agent workflow.

```text
Manifest/
├── README.md                        # Human-readable documentation
├── AGENTS.md                        # AI-readable documentation (this file)
├── CLAUDE.md                        # Claude-specific project context
├── configs/                         # Deployment source configs
│   ├── claude/                      # Primary config source (canonical)
│   │   ├── CLAUDE.md                # Developer guide for this repo
│   ├── skills/                      # Canonical shared skill library
│   ├── prompts/                     # Shared prompts (orchestration, synthesis)
│   ├── config/                      # YAML configuration files
│   │   └── mcp_servers.yml          # Default MCP server registry
│   ├── .plans/                      # Plan management (template, archive)
│   ├── scripts/                     # Orchestration scripts (parallel_agent.py)
│   └── settings.local.json          # Default permissions
│   ├── cursor/                      # Cursor-specific config
│   │   ├── rules/                   # Cursor rules (.mdc) — auto-generated
│   │   └── mcp.json                 # Cursor MCP settings
│   ├── gemini/                      # Gemini-specific config
│   │   ├── GEMINI.md                # Orchestration guide for Gemini
│   │   ├── settings.json            # Gemini settings (includes MCP defaults)
│   │   └── (symlinks to ../claude/) # Scripts, skills, prompts mirrored
│   └── codex/                       # Codex-specific config
│       ├── AGENTS.md                # Codex guide (symlink to AGENTS.md)
│       └── (symlinks to ../claude/) # Scripts, skills, prompts mirrored
├── .claude/                         # Repo-specific config (minimal)
│   ├── CLAUDE.md                    # Project context for Manifest itself
│   ├── settings.local.json          # Repo permissions
│   ├── .plans/                      # Repo-specific plans
│   ├── node/                        # package.json, tsconfig.json
│   └── scripts/                     # Repo-specific scripts
├── bootstrap.sh                     # Main entry point (calls lib/*.sh)
└── bootstrap/                       # Modular bootstrap libraries
    ├── lib/
    │   ├── common.sh                # Shared bootstrap helpers
    │   ├── modules.sh               # Module loader + hooks
    │   ├── platform.sh              # Platform detection
    │   ├── config.sh                # Argument parsing
    │   ├── install.sh               # CLI installation routines
    │   ├── auth.sh                  # Authentication routines
    │   ├── deploy.sh                # Deployment routines
    │   └── mcp.sh                   # MCP routines
```

## Setup & Deployment

The `bootstrap.sh` script automates installation, deployment, and
authentication. It ensures all agents have the correct configuration, skills,
and permissions.

### Common Commands

```bash
# Standard deployment (safe, idempotent)
./bootstrap.sh

# Install specific components
./bootstrap.sh --enable-cursor --disable-gemini

# Full reconfiguration (interactive)
./bootstrap.sh --reconfigure

# Install MCP servers
./bootstrap.sh --install-mcp

# Advanced flags
--install-mcp                        # Configure MCP servers (interactive)
--reconfigure                        # Force reconfiguration of services
--force                              # Skip confirmations
--verbose                            # Enable debug logging
```

## Agent Orchestration

Manifest uses a **Parallel Agent Architecture** where tasks are distributed
across multiple models.

### Key Components

| Component | Description |
|-----------|-------------|
| `configs/cursor/rules/orchestration.mdc` | Main Cursor orchestration guide |
| `configs/gemini/GEMINI.md` | Main Gemini orchestration guide |
| `configs/claude/CLAUDE.md` | Main Claude orchestration guide |
| `configs/claude/scripts/parallel_agent.sh` | Parallel agent script |
| `configs/claude/config/command_config.yml` | Thresholds, policies, models |
| `configs/claude/config/validation_criteria.yml` | Validation rules |

### Skills Library

All agents share the same skill library from `configs/claude/skills/` (25
skills). Skills are exposed differently per platform:

**Key Skills:**

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/plan-manage` | Plan lifecycle with parallel orchestration | CONDITIONAL |
| `/project-commit` | Full commit pipeline: docs, push | CONDITIONAL |
| `/issue-triage` | Linear issue audit: duplicates, priority | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues | CONDITIONAL |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL |
| `/refactor-terraform` | Terraform IaC security analysis | ALWAYS |
| `/scaffold` | Initialize new project with quality gates | NO |

## Development Guidelines

When modifying this repository, follow these rules:

1.  **Single Source of Truth**: Edit skills in `configs/claude/skills/`. Do NOT
    edit platform-specific copies (e.g., `~/.cursor/rules/`).
2.  **Idempotency**: All scripts (especially `bootstrap.sh`) must be safe to
    run multiple times.
3.  **Cross-Platform**: Support macOS (Darwin) and Linux
    (Debian/RHEL/Arch/Suse). Use `bootstrap/lib/platform.sh` helpers.
4.  **Parallel Execution**: Test changes with `parallel_agent.py` to ensure
    consensus scoring works.

### Editing Cursor Rules

All Cursor rules are auto-generated from SKILL.md files using
`generate_cursor_rules.sh`. Do NOT edit `.mdc` files in `configs/cursor/rules/`
directly. Edit the source `SKILL.md` instead.

### Symlink Strategy

Skills are shared across all platforms via symlinks from
`configs/claude/skills/`:

- **Claude Code**: Loaded directly from `~/.claude/skills/`
- **Cursor**: Rules auto-generated into `~/.cursor/rules/` (`.mdc` files)
- **Gemini CLI**: Skills loaded from `~/.gemini/skills/` (symlinked)
- **Codex CLI**: Skills loaded from `~/.codex/skills/` (symlinked)

## Testing

### Parallel Agent Script

All agents share the same orchestration script at
`configs/claude/scripts/parallel_agent.sh`. This script runs agents in parallel
and calculates consensus.

```bash
# Run review on a file with 10 minute timeout
~/.claude/scripts/parallel_agent.sh --json --timeout 600 \
  --review /absolute/path/to/file

# Run analysis with validation
~/.claude/scripts/parallel_agent.sh --json --full-output --validate \
  --timeout 900 --analyze /absolute/path/to/file
```

### Config Validation

Validate YAML configuration files:

```bash
python3 -c "import yaml; \
  yaml.safe_load(open('configs/claude/config/command_config.yml'))"
python3 -c "import yaml; \
  yaml.safe_load(open('configs/claude/config/validation_criteria.yml'))"
```

## Plan Management

Implementation plans are tracked in `configs/claude/.plans/` (symlinked at
`configs/cursor/.plans/`, `configs/gemini/.plans/`, and `configs/codex/.plans/`)
as date-prefixed markdown files (`YYYYMMDD-description.md`).

Lifecycle: `CREATE` -> `ACTIVE` -> `COMPLETED` (.archive/) or `ABANDONED`

## Creating New Skills

To add a new capability:

1. Create a `SKILL.md` file in `configs/claude/skills/my-skill/`
2. Define `description`, `globs`, and `instructions` in the frontmatter
3. Skills are automatically available in Claude Code after deploying

**For Cursor:**

1. Ensure the skill has a valid `SKILL.md`
2. Run `./bootstrap.sh` to regenerate Cursor rules
3. Rule auto-attaches when files matching `globs` are referenced

**For Gemini:**

Gemini CLI uses the shared skills from `configs/claude/skills/` (symlinked at
`~/.gemini/skills`). Orchestration is handled via `~/.gemini/GEMINI.md`
system instructions.

## Documentation Index

- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) - Setup walkthrough
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Configuration reference
- [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) - Visual docs
- [configs/claude/.plans/README.md](configs/claude/.plans/README.md) - Plans
