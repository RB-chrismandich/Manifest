# AGENTS.md

> Repository context and guidance for AI coding agents
> (Cursor, Claude Code, Gemini, Codex, etc.)

**Last Updated**: 2026-02-11
**Audience**: AI assistants (Cursor, Claude, Gemini, Codex), contributors
**Purpose**: Provide AI agents with repo structure, deployment, and test guides

---

This file provides guidance to AI coding agents when working with code in this repository.
It follows the [AGENTS.md standard](https://agents.md/) for agent instructions.

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

This repository manages AI agent configurations for deployment to `~/.claude/`
(and mirrored
to `~/.cursor/`, `~/.gemini/`, and `~/.codex/`) on target machines.
It contains orchestration guides,
skills, prompts, and scripts that enable parallel LLM agent coordination
(Cursor, Gemini CLI, Claude CLI, Codex CLI).

## Repository Structure

```text
configs/                             # Deployment source configs
├── claude/                          # → ~/.claude/ (primary configuration)
│   ├── CLAUDE.md                    # Orchestration guide
│   ├── skills/                      # Shared skill library (source of truth)
│   ├── prompts/                     # Agent orchestration prompt templates
│   ├── config/                      # YAML config files
│   │   └── mcp_servers.yml          # Default MCP server registry
│   ├── .plans/                      # Plan management (template, archive, abandoned)
│   ├── settings.local.json          # Default permissions and MCP server config
│   └── scripts/parallel_agent.sh    # Main parallel agent orchestration script
├── cursor/                          # → ~/.cursor/ (Cursor IDE configuration)
│   ├── rules/                       # Cursor rules (.mdc) (auto-generated)
│   ├── mcp.json                     # Cursor MCP server defaults
│   ├── scripts -> ../claude/scripts # Symlink to shared scripts
│   ├── config -> ../claude/config   # Symlink to shared configs
│   ├── prompts -> ../claude/prompts # Symlink to shared prompts
│   ├── skills -> ../claude/skills   # Shared skills symlink
│   └── .plans -> ../claude/.plans   # Symlink to shared plans
├── gemini/                          # → ~/.gemini/ (Gemini CLI configuration)
│   ├── GEMINI.md                    # Orchestration guide for Gemini CLI
│   ├── settings.json                # Gemini settings (includes MCP defaults)
│   ├── scripts -> ../claude/scripts # Symlink to shared scripts
│   ├── config -> ../claude/config   # Symlink to shared configs
│   ├── prompts -> ../claude/prompts # Symlink to shared prompts
│   ├── skills -> ../claude/skills   # Shared skills symlink
│   └── .plans -> ../claude/.plans   # Symlink to shared plans
└── codex/                           # → ~/.codex/ (Codex CLI configuration)
    ├── AGENTS.md -> ../../AGENTS.md # Codex guide (repo-level instructions)
    ├── scripts -> ../claude/scripts # Symlink to shared scripts
    ├── config -> ../claude/config   # Symlink to shared configs
    ├── prompts -> ../claude/prompts # Symlink to shared prompts
    ├── skills -> ../claude/skills   # Shared skills symlink
    └── .plans -> ../claude/.plans   # Symlink to shared plans

.claude/                             # Repo-specific config
├── CLAUDE.md                        # Developer guide for working in this repo
└── settings.local.json              # Repo-relevant permissions only

templates/                           # Project scaffolding templates
├── scaffold/
│   ├── python/                      # pyproject.toml, .pre-commit-config.yaml
│   ├── go/                          # go.mod, Makefile, .golangci.yml
│   ├── node/                        # package.json, tsconfig.json, eslint.config.js
│   └── terraform/                   # main.tf, versions.tf, .tflint.hcl

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
--install-mcp                        # Configure MCP servers (interactive)
```

## Manual Deployment

If not using bootstrap.sh, copy the configuration directories manually:

```bash
# Deploy Claude Code configuration
cp -r configs/claude/* ~/.claude/
cp -r configs/claude/.[!.]* ~/.claude/ 2>/dev/null || true
chmod +x ~/.claude/scripts/*.sh

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
| ------ | --------- |
| `configs/claude/CLAUDE.md` | Main orchestration guide for Claude Code |
| `configs/cursor/rules/orchestration.mdc` | Cursor orchestration guide |
| `configs/gemini/GEMINI.md` | Main orchestration guide for Gemini CLI |
| `configs/codex/AGENTS.md` | Main orchestration guide for Codex CLI |
| `configs/claude/scripts/parallel_agent.sh` | Parallel agent Bash script |
| `configs/claude/config/command_config.yml` | Thresholds, policies, models |
| `configs/claude/config/validation_criteria.yml` | Validation rules |

## Available Skills

All agents share the same skill library from `configs/claude/skills/`.
Skills are invoked as slash commands (e.g., `/refactor-python src/`).

### Skill Reference

| Skill | Description | Parallel Agents |
| ------- | ------------- | ----------------- |
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/antipattern-detect` | Detect codebase antipatterns and suggest fixes | NO |
| `/checkpoint` | Save context checkpoint for session continuity | NO |
| `/ci-setup` | Configure CI/CD pipelines for target repository | NO |
| `/code-quality` | Auto-triggered security and quality checks | AUTO |
| `/dashboard` | Visualize agent efficiency metrics | NO |
| `/docs-diagrams` | Generate Mermaid diagrams | CONDITIONAL |
| `/docs-improve` | Diataxis documentation | CONDITIONAL |
| `/docs-readme` | Improve README documentation | NO |
| `/health-check` | Verify CLI tools, auth, config, MCP, symlinks | NO |
| `/issue-prioritize` | Score and rank open issues by impact | CONDITIONAL |
| `/issue-triage` | Linear issue audit with duplicate detection | CONDITIONAL |
| `/learning-loop` | Capture structured lessons learned | NO |
| `/performance-check` | Core Web Vitals and bundle analysis | NO |
| `/plan-manage` | Plan lifecycle with parallel agent | CONDITIONAL |
| `/project-commit` | Commit pipeline: docs, pull, push | CONDITIONAL |
| `/refactor-go` | Go codebase security and quality analysis | ALWAYS |
| `/refactor-node` | Node.js/TS security/quality | ALWAYS |
| `/refactor-python` | Python codebase security/quality | ALWAYS |
| `/refactor-shell` | Shell script security/quality | ALWAYS |
| `/refactor-terraform` | Terraform security/modularity | ALWAYS |
| `/scaffold` | Initialize new project with quality gates | NO |
| `/sync-configs` | Detect cross-platform config drift | NO |
| `/ux-review` | UX/accessibility/performance audit | NO |
| `/verify` | Run linters, tests, and security scans in parallel | CONDITIONAL |

### Cursor Rules

Cursor rules are auto-generated from SKILL.md via `generate_cursor_rules.sh`.
Each skill produces a corresponding `.mdc` rule in `configs/cursor/rules/`.

| Rule | Description |
| ------ | ------------- |
| `orchestration` | Parallel agent orchestration guide (always-on) |
| `a11y-audit` | WCAG 2.2 AA accessibility audit |
| `antipattern-detect` | Codebase antipattern detection |
| `checkpoint` | Context checkpoint |
| `ci-setup` | CI/CD pipeline configuration |
| `code-quality` | Auto-triggered security/quality checks |
| `dashboard` | Efficiency metrics |
| `docs-diagrams` | Mermaid diagram generation |
| `docs-improve` | Diataxis documentation |
| `docs-readme` | README improvement |
| `health-check` | Environment health check |
| `issue-prioritize` | Issue prioritization |
| `issue-triage` | Linear issue triage |
| `learning-loop` | Lessons learned capture |
| `performance-check` | Performance analysis |
| `plan-manage` | Plan lifecycle |
| `project-commit` | Commit pipeline |
| `refactor-go` | Go analysis |
| `refactor-node` | Node.js/TypeScript analysis |
| `refactor-python` | Python analysis |
| `refactor-shell` | Shell analysis |
| `refactor-terraform` | Terraform IaC analysis |
| `scaffold` | Project scaffolding |
| `sync-configs` | Config drift detection |
| `ux-review` | UX/accessibility audit |
| `verify` | Linter/test/security scan runner |

### Platform-Specific Notes

Skills are shared across all platforms via symlinks from `configs/claude/skills/`:

- **Claude Code**: Skills loaded from `~/.claude/skills/`
- **Cursor**: Rules auto-generated from skills into `~/.cursor/rules/` (`.mdc` files)
- **Gemini CLI**: Skills loaded from `~/.gemini/skills/` (symlink to `~/.claude/skills/`)
- **Codex CLI**: Skills loaded from `~/.codex/skills/` (symlink to `~/.claude/skills/`)

## Parallel Agent Orchestration

All agents share the same orchestration script at `configs/claude/scripts/parallel_agent.sh`.

```bash
# Basic code review (all 3 agents)
~/.claude/scripts/parallel_agent.sh --json --timeout 600 --review /absolute/path/to/file

# Security analysis with maximum capability models
~/.claude/scripts/parallel_agent.sh --json --validate --timeout 900 \
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
configs/claude/scripts/parallel_agent.sh --json "Test prompt"

# Test specific mode
configs/claude/scripts/parallel_agent.sh --json --review /path/to/file

# Validate YAML configs
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/validation_criteria.yml'))"
```

## Plan Management

Plans are tracked in `configs/claude/.plans/` (symlinked to other platforms,
like `~/.cursor/.plans/`) as date-prefixed files (`YYYYMMDD-description.md`).

Lifecycle: `CREATE -> ACTIVE -> COMPLETED (.archive/) or ABANDONED (.abandoned/)`

## Adding New Configuration

### Adding a Claude Code Skill

1. Create a `SKILL.md` file in `configs/claude/skills/my-skill/`
2. Add tool policies to `configs/claude/config/command_config.yml`
3. Skills are automatically available after deploying via bootstrap

### Adding a Cursor Rule

1. Create an `.mdc` file in `configs/cursor/rules/` (e.g., `my-rule.mdc`)
2. Add YAML frontmatter with `description`, `globs`, and `alwaysApply`
3. Rule auto-attaches when files matching `globs` are referenced

### Adding a Gemini CLI Skill

Gemini CLI uses shared skills from `configs/claude/skills/`.
To add a new skill, follow the Claude Code skill instructions above.

---

## Related Documents

- [README.md](README.md) - Project overview and quick start
- [CLAUDE.md](CLAUDE.md) - Claude Code-specific project instructions
- [docs/README.md](docs/README.md) - Documentation hub
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) - First-time setup walkthrough
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Complete configuration reference
- [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) - Architecture
- [configs/claude/.plans/README.md](configs/claude/.plans/README.md) - Plans info
