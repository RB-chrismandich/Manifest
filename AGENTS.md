# AGENTS.md

> Repository context and guidance for AI coding agents (Cursor, Claude Code, Gemini, Codex, etc.)

**Last Updated**: 2026-02-11
**Audience**: AI assistants (Cursor Agent, Claude Code, Gemini CLI, Codex CLI), contributors
**Purpose**: Provide AI agents with repository structure, deployment process, and testing guidelines

---

This file provides guidance to AI coding agents when working with code in this repository.
It follows the [AGENTS.md standard](https://agents.md/) for unified coding agent instructions.

## MCP Default Policy

Use these MCP servers by default when their domain context matches the task:

- **Context7 MCP**: library/API documentation, code generation, setup steps,
  and configuration guidance.
- **Sentry MCP**: production/runtime error investigation, stack traces, issue
  triage, and release regression analysis.
- **Linear MCP**: issue requirements, acceptance criteria, project context, and
  implementation planning.

## Repository Purpose

This repository manages AI agent configurations for deployment to `~/.claude/` (and mirrored
to `~/.cursor/`, `~/.gemini/`, and `~/.codex/`) on target machines. It contains orchestration guides,
commands/rules, skills, prompts, and scripts that enable parallel LLM agent coordination
(Cursor, Gemini CLI, Claude CLI, Codex CLI).

## Repository Structure

```text
.claude/                             # Primary configuration (Claude Code)
├── CLAUDE.md                        # Orchestration guide (deployed to ~/.claude/)
├── commands/                        # Claude Code slash commands
├── skills/                          # Canonical shared skill library (source of truth)
├── prompts/                         # Agent orchestration prompt templates
├── config/                          # YAML configuration files
│   └── mcp_servers.yml              # Default MCP server registry (OAuth-capable)
├── .plans/                          # Plan management (template, archive, abandoned)
└── scripts/parallel_agent.sh        # Main parallel agent orchestration script

.cursor/                             # Cursor IDE configuration (mirrors .claude/)
├── rules/                           # Cursor rules (.mdc) — auto-generated from SKILL.md (25+)
├── mcp.json                         # Cursor MCP server defaults
├── scripts -> ../.claude/scripts/   # Symlink to shared scripts
├── config -> ../.claude/config/     # Symlink to shared configs
├── prompts -> ../.claude/prompts/   # Symlink to shared prompts
├── skills -> ../.claude/skills      # Shared skills symlink (single source of truth)
└── .plans -> ../.claude/.plans/     # Symlink to shared plans

.gemini/                             # Gemini CLI configuration (mirrors .claude/)
├── GEMINI.md                        # Orchestration guide for Gemini CLI
├── commands/                        # TOML slash commands (23)
├── settings.json                    # Gemini settings (includes MCP server defaults)
├── skills -> ../.claude/skills      # Shared skills symlink (single source of truth)
├── scripts -> ../.claude/scripts/   # Symlink to shared scripts
├── config -> ../.claude/config/     # Symlink to shared configs
├── prompts -> ../.claude/prompts/   # Symlink to shared prompts
└── .plans -> ../.claude/.plans/     # Symlink to shared plans

templates/                           # Project scaffolding templates
├── scaffold/
│   ├── python/                      # pyproject.toml, .pre-commit-config.yaml
│   ├── go/                          # go.mod, Makefile, .golangci.yml
│   ├── node/                        # package.json, tsconfig.json, eslint.config.js
│   └── terraform/                   # main.tf, versions.tf, .tflint.hcl

.codex/                              # Codex CLI configuration (mirrors .claude/)
├── AGENTS.md -> ../AGENTS.md        # Codex guide (repo-level instructions)
├── commands -> ../.claude/commands  # Command-style wrappers (shared with Claude)
├── skills -> ../.claude/skills      # Shared skills symlink (single source of truth)
├── scripts -> ../.claude/scripts/   # Symlink to shared scripts
├── config -> ../.claude/config/     # Symlink to shared configs
├── prompts -> ../.claude/prompts/   # Symlink to shared prompts
└── .plans -> ../.claude/.plans/     # Symlink to shared plans

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

# Configure default MCP servers (sentry, context7, linear)
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
--install-mcp                        # Configure default MCP servers (sentry/context7/linear)
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
cp .cursor/mcp.json ~/.cursor/mcp.json
# Recreate symlinks for shared assets
ln -sf ~/.claude/scripts ~/.cursor/scripts
ln -sf ~/.claude/config ~/.cursor/config
ln -sf ~/.claude/prompts ~/.cursor/prompts
ln -sf ~/.claude/.plans ~/.cursor/.plans
ln -sf ~/.claude/skills ~/.cursor/skills

# Deploy Gemini configuration (optional)
mkdir -p ~/.gemini/commands
cp .gemini/GEMINI.md ~/.gemini/
cp .gemini/commands/*.toml ~/.gemini/commands/
cp .gemini/settings.json ~/.gemini/settings.json
ln -sf ~/.claude/scripts ~/.gemini/scripts
ln -sf ~/.claude/config ~/.gemini/config
ln -sf ~/.claude/prompts ~/.gemini/prompts
ln -sf ~/.claude/.plans ~/.gemini/.plans
ln -sf ~/.claude/skills ~/.gemini/skills

# Deploy Codex configuration (optional)
cp AGENTS.md ~/.codex/AGENTS.md
ln -sf ~/.claude/commands ~/.codex/commands
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
| `.claude/CLAUDE.md` | Main orchestration guide for Claude Code |
| `.cursor/rules/orchestration.mdc` | Main orchestration guide for Cursor (always-on rule) |
| `.gemini/GEMINI.md` | Main orchestration guide for Gemini CLI |
| `.codex/AGENTS.md` | Main orchestration guide for Codex CLI |
| `.codex/commands/` | Codex command-style wrappers (shared with Claude command files) |
| `.claude/scripts/parallel_agent.sh` | Bash script that runs agents in parallel with consensus scoring |
| `.claude/config/command_config.yml` | Thresholds, tool policies, model selection, error recovery |
| `.claude/config/validation_criteria.yml` | Tier 1 (critical) and Tier 2 (quality) validation rules |

## Available Commands / Rules

### Claude Code Commands

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/project-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL |
| `/refactor-python` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-go` | Go codebase security and quality analysis | ALWAYS |
| `/refactor-node` | Node.js/TypeScript security and quality analysis | ALWAYS |
| `/refactor-terraform` | Terraform IaC security and modularity analysis | ALWAYS |
| `/refactor-shell` | Bash/Shell script security and quality analysis | ALWAYS |
| `/scaffold` | Initialize new project with quality gates and Manifest integration | NO |
| `/verify` | Run linters, tests, and security scans in parallel | CONDITIONAL |
| `/ci-setup` | Configure CI/CD pipelines for target repository | NO |
| `/ux-review` | UX/accessibility/performance audit | NO |
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/performance-check` | Core Web Vitals and bundle analysis | NO |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL |
| `/docs-readme` | Improve README documentation | NO |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |
| `/issue-triage` | Linear issue audit with duplicate detection | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues by impact | CONDITIONAL |
| `/health-check` | Verify CLI tools, auth, config, MCP, symlinks | NO |
| `/sync-configs` | Detect cross-platform config drift | NO |
| `/learning-loop` | Capture structured lessons learned | NO |
| `/dashboard` | Visualize agent efficiency metrics | NO |
| `/checkpoint` | Save context checkpoint for session continuity | NO |

### Cursor Rules

All Cursor rules are auto-generated from SKILL.md files using `generate_cursor_rules.sh`.

| Rule | Description |
|------|-------------|
| `orchestration` | Parallel agent orchestration guide (always-on) |
| `code-quality` | Auto-triggered security/quality checks |
| `refactor-python` | Python analysis |
| `refactor-go` | Go analysis |
| `refactor-node` | Node.js/TypeScript analysis |
| `refactor-terraform` | Terraform IaC analysis |
| `refactor-shell` | Shell analysis |
| `scaffold` | Project scaffolding |
| `verify` | Linter/test/security scan runner |
| `ci-setup` | CI/CD pipeline configuration |
| `ux-review` | UX/accessibility audit |
| `a11y-audit` | WCAG 2.2 AA accessibility audit |
| `performance-check` | Performance analysis |
| `docs-readme` | README improvement |
| `docs-improve` | Diataxis documentation |
| `docs-diagrams` | Mermaid diagram generation |
| `project-commit` | Commit pipeline |
| `plan-manage` | Plan lifecycle |
| `issue-triage` | Linear issue triage |
| `issue-prioritize` | Issue prioritization |
| `health-check` | Environment health check |
| `sync-configs` | Config drift detection |
| `learning-loop` | Lessons learned capture |
| `dashboard` | Efficiency metrics |
| `checkpoint` | Context checkpoint |

### Gemini CLI Commands

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/project-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL |
| `/refactor-python` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-go` | Go codebase security and quality analysis | ALWAYS |
| `/refactor-node` | Node.js/TypeScript security and quality analysis | ALWAYS |
| `/refactor-terraform` | Terraform IaC security and modularity analysis | ALWAYS |
| `/refactor-shell` | Bash/Shell script security and quality analysis | ALWAYS |
| `/scaffold` | Initialize new project with quality gates | NO |
| `/verify` | Run linters, tests, and security scans | CONDITIONAL |
| `/ci-setup` | Configure CI/CD pipelines | NO |
| `/ux-review` | UX/accessibility audit | NO |
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/performance-check` | Core Web Vitals and bundle analysis | NO |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL |
| `/docs-readme` | Improve README documentation | NO |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |
| `/issue-triage` | Linear issue audit with duplicate detection | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues by impact | CONDITIONAL |
| `/health-check` | Verify CLI tools, auth, config, MCP, symlinks | NO |
| `/sync-configs` | Detect cross-platform config drift | NO |
| `/learning-loop` | Capture structured lessons learned | NO |
| `/dashboard` | Visualize agent efficiency metrics | NO |
| `/checkpoint` | Context checkpoint for session continuity | NO |

### Shared Skills

Shared skills are canonical in `.claude/skills/` and symlinked to:

- `~/.cursor/skills`
- `~/.gemini/skills`
- `~/.codex/skills`

Current skills: `code-quality`, `project-commit`, `refactor-python`, `refactor-go`,
`refactor-node`, `refactor-terraform`, `refactor-shell`, `scaffold`, `verify`, `ci-setup`,
`ux-review`, `a11y-audit`, `performance-check`, `docs-diagrams`, `docs-improve`, `docs-readme`,
`plan-manage`, `issue-triage`, `issue-prioritize`, `health-check`, `sync-configs`,
`learning-loop`, `dashboard`, `antipattern-detect`, `checkpoint`.

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

Implementation plans are tracked in `.claude/.plans/` (symlinked at `.cursor/.plans/`,
`.gemini/.plans/`, and `.codex/.plans/`) as date-prefixed markdown files (`YYYYMMDD-description.md`).

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
