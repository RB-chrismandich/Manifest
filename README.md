# Manifest

[![Manifest CI](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml/badge.svg)](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml)

> Parallel LLM agent orchestration framework for Claude Code, Cursor IDE, Gemini CLI, and Codex CLI

**Last Updated**: 2026-05-31

Manifest is a configuration repository that deploys a sophisticated parallel agent
orchestration system to `~/.claude/`, `~/.cursor/`, `~/.gemini/`, and `~/.codex/`, enabling Claude Code,
Cursor IDE, Gemini CLI, and Codex CLI to share guides, skills, prompts, and scripts while leveraging
multiple AI agents for cross-verification, consensus scoring, and enhanced code analysis.

**Core Capabilities**: Multi-agent orchestration | Consensus scoring | Model fallback
| Two-tier validation | Production-grade templates

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/ReefBytes/Manifest.git
cd Manifest

# Run bootstrap (macOS/Linux)
./bootstrap.sh

# Optional: configure MCP servers (interactive per-server selection)
./bootstrap.sh --install-mcp

# Verify installation
~/.claude/scripts/parallel_agent.py --json "Test connection"
```

⏱️ **Time to setup**: ~5 minutes | 💻 **Platforms**: macOS (Intel/Apple Silicon), Linux (Debian, RHEL, Arch, openSUSE)
🐍 **Python**: 3.9+ (Phase 3 features require Python; bootstrap auto-detects and prefers 3.12+)

---

## Features

- **Parallel Agent Orchestration**: Run 2-4 AI agents simultaneously
  (Cursor, Gemini, Claude, Codex) with real-time streaming display
- **Modular `agents/` Package**: `parallel_agent.py` backed by `agents/` subpackage —
  `cli.py`, `config.py`, `orchestrator.py`, `runners.py`, `synthesis.py`, `validation.py`
- **Comprehensive Logging**: Structured JSON logs with correlation IDs, rotation (10MB, 5 backups), performance metrics
- **Full Validation Engine**: Tier 1 (critical: security, errors, breaking changes)
  \+ Tier 2 (quality: bugs, performance, tests)
- **Automatic Synthesis**: Disagreement resolution when consensus < 50% using Claude Sonnet
- **Streaming Responses**: Real-time Rich Live display with progressive updates (4 updates/sec)
- **Consensus Scoring**: Variance-based algorithm calculates agreement (≥80% = high confidence, <50% = escalate + synthesis)
- **Intelligent Model Selection**: Task-based routing (security→opus/gpt-5.2, review→sonnet/gpt-5.1-codex, quick→haiku/mini)
- **Credit Exhaustion Fallback**: Automatic detection and retry with cheaper models (opus→sonnet→haiku)
- **Cross-Platform**: Native support for macOS (Intel/Apple Silicon) and 5 major Linux distributions
- **Unified Label Management**: Canonical label registry with sync across GitHub, GitLab, and Linear
- **Production Templates**: Pre-configured permission templates for Django, Express, Go microservices, Python monorepos

---

## Architecture

```text
User → Claude Code → /command → parallel_agent.py
                                      ↓
                    ┌────────────┬────┼────┬────────────┐
                    ↓            ↓         ↓            ↓
              Cursor Agent  Gemini CLI  Claude CLI  Codex CLI
              (IDE Context) (Broad      (Deep       (Terminal
                            Knowledge)  Reasoning)   Coding)
                    ↓            ↓         ↓            ↓
                    └────────────┴────┼────┴────────────┘
                                      ↓
                            Synthesis & Validation
                                      ↓
                                  JSON Output
```

**Visual Documentation**: [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) -
Mermaid flowcharts showing bootstrap, execution, validation, and consensus flows

---

## Available Commands

| Command | Description | Parallel Agents | Validation |
|---------|-------------|-----------------|------------|
| `/project-commit` | Full commit pipeline: regenerate docs, pull latest, run pre-commits, commit, push | CONDITIONAL | Tier 1 + Tier 2 |
| `/refactor-python` | Python security, architecture, code quality analysis | ALWAYS | Tier 1 + Tier 2 (≥0.80) |
| `/refactor-shell` | Bash/Shell script security and quality with shellcheck | ALWAYS | Tier 1 + Tier 2 (≥0.70) |
| `/docs-diagrams` | Generate Mermaid architecture flowcharts and sequence diagrams | CONDITIONAL (≥5 imports) | Tier 2 |
| `/docs-improve` | Analyze docs against Diataxis framework (tutorials, how-tos, reference, explanation) | CONDITIONAL (≥500 lines) | Tier 2 |
| `/docs-readme` | Improve README structure and content following best practices | NEVER | Tier 2 |
| `/issue-prioritize` | Fetch and rank open issues by impact, urgency, readiness, risk (GitHub/GitLab/Linear) | CONDITIONAL (top candidates) | Tier 2 |
| `/issue-triage` | Linear issue audit: duplicates, staleness, priority validation | CONDITIONAL (scenario-based) | Tier 2 |
| `/plan-manage` | Plan lifecycle: create, review, execute, archive, abandon | CONDITIONAL | Tier 2 |
| `/browser-test` | AI-powered E2E browser testing via browser-use YAML test prompts | CONDITIONAL | Tier 2 |

**CLI tools** (installed to `~/.local/bin/`):

| Tool | Description |
|------|-------------|
| `sync-skills` | Sync `.skillshare/skills/` to all home targets; requires `MANIFEST_ROOT` env var |

---

## Requirements

**For bootstrap.sh (automated setup):**

- macOS 10.15+ or Linux (Debian/Ubuntu, RHEL/Fedora, Arch, openSUSE)
- Internet connection for package downloads
- npm-compatible environment (auto-installed if missing)

**For manual setup:**

- Bash 4.0+
- Node.js 18+ and npm
- One or more of: Claude CLI, Gemini CLI, Cursor Agent, Codex CLI

**For `parallel_agent.py` (Python agent):**

- Python 3.9+ (3.12+ recommended, auto-detected by bootstrap)
- Install deps: `pip install -r configs/claude/scripts/requirements.txt`
- Key packages: `anthropic`, `google-genai`, `rich`, `pyyaml`, `aiohttp`

---

## Documentation

| Document | Purpose | Audience | Reading Time |
|----------|---------|----------|--------------|
| [Getting Started](docs/GETTING_STARTED.md) | First-time setup walkthrough with verification steps | New users | 10 min |
| [Configuration](docs/CONFIGURATION.md) | All configuration options, YAML reference, environment variables | Operators | 15 min |
| [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) | Visual system documentation with 14 Mermaid diagrams | Developers | 20 min |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common problems, error messages, solutions | All users | 10 min |
| [AGENTS.md](AGENTS.md) | AI agent instructions (Cursor, Claude, Gemini, Codex) | AI assistants | 8 min |
| [CLAUDE.md](CLAUDE.md) | Claude Code-specific project context | AI assistants | 8 min |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines, testing, commit conventions | Contributors | 5 min |
| [CHANGELOG.md](CHANGELOG.md) | Version history and notable changes | All | 5 min |

**Full documentation index**: [docs/README.md](docs/README.md) • **Quick ref**: [Commands](docs/COMMANDS.md)

---

## Project Structure

```text
Manifest/
├── bootstrap.sh                     # Cross-platform installation script (macOS/Linux)
├── bootstrap/                       # Modular bootstrap libraries and extension hooks
│   ├── lib/
│   │   ├── common.sh                # Shared bootstrap helpers (output, prompts, symlinks)
│   │   ├── modules.sh               # Module loader + lifecycle hook registry
│   │   ├── platform.sh              # Platform detection + timeout/browser helpers
│   │   ├── config.sh                # Arg parsing + service config read/write helpers
│   │   ├── install.sh               # CLI installation routines
│   │   ├── auth.sh                  # Authentication + state setup routines
│   │   ├── deploy.sh                # Deployment/verification/summary routines
│   │   └── mcp.sh                   # MCP installation/configuration routines
│   └── modules/README.md            # How to add custom bootstrap modules/hooks
├── CLAUDE.md                        # Claude Code project context
├── AGENTS.md                        # AI agent instructions (all platforms)
├── configs/                         # Deployment source configs (deployed to ~/ via bootstrap)
│   ├── claude/                      # → ~/.claude/ (primary configuration)
│   │   ├── CLAUDE.md                # Orchestration guide
│   │   ├── skills/                  # → ../../.skillshare/skills (symlink; source of truth)
│   │   ├── prompts/                 # Agent orchestration templates
│   │   ├── config/                  # YAML configuration files
│   │   │   ├── services.yml         # Agent enable/disable states
│   │   │   ├── mcp_servers.yml      # Default MCP server registry
│   │   │   ├── command_config.yml   # Tool policies, thresholds, model selection
│   │   │   ├── validation_criteria.yml # Tier 1/2 validation rules
│   │   │   └── labels.yml           # Canonical label registry
│   │   ├── scripts/                 # Orchestration scripts
│   │   │   ├── parallel_agent.py    # Entry point shim (delegates to agents/)
│   │   │   ├── agents/              # Modular orchestration package
│   │   │   │   ├── cli.py           # Argparse + main() coroutine
│   │   │   │   ├── orchestrator.py  # Parallel execution + consensus scoring
│   │   │   │   ├── runners.py       # Agent classes (Claude/Gemini/Cursor/Codex)
│   │   │   │   ├── config.py        # Config, Logger, RateLimiter, ServiceConfig
│   │   │   │   ├── synthesis.py     # Disagreement resolution engine
│   │   │   │   └── validation.py    # Tier 1/2 validation engine
│   │   │   ├── git_platform.sh      # Git platform detection
│   │   │   ├── git_ops.sh           # Platform-agnostic Git operations
│   │   │   ├── linear_ops.sh        # Linear API wrapper (GraphQL)
│   │   │   ├── sync-skills.sh       # Skill deployment to home targets
│   │   │   └── label_sync.sh        # Label provisioning across platforms
│   │   └── settings.local.json      # Default permissions + MCP servers
│   ├── cursor/                      # → ~/.cursor/ (Cursor IDE)
│   │   ├── rules/                   # Cursor rules (.mdc) adapted from skills
│   │   ├── mcp.json                 # Cursor MCP server defaults
│   │   └── (symlinks to ../claude/) # scripts, config, prompts, skills, .plans
│   ├── gemini/                      # → ~/.gemini/ (Gemini CLI)
│   │   ├── GEMINI.md                # Orchestration guide for Gemini
│   │   ├── settings.json            # Gemini settings
│   │   └── (symlinks to ../claude/) # scripts, config, prompts, skills, .plans
│   └── codex/                       # → ~/.codex/ (Codex CLI)
│       ├── AGENTS.md                # Codex guide (symlink to ../../AGENTS.md)
│       └── (symlinks to ../claude/) # scripts, config, prompts, skills, .plans
├── .claude/                         # Repo-specific config only (does NOT override sessions)
│   ├── CLAUDE.md                    # Developer guide for working in this repo
│   └── settings.local.json          # Repo-relevant permissions only
├── templates/                       # Starter templates for CI and project scaffolding
│   ├── ci/                          # CI configuration templates
│   │   ├── github/                  # GitHub Actions workflow templates
│   │   └── gitlab/                  # GitLab CI pipeline templates
│   └── scaffold/                    # Project scaffolding templates
│       ├── go/                      # Go project starter
│       ├── node/                    # Node.js project starter
│       ├── python/                  # Python project starter
│       └── terraform/               # Terraform project starter
├── .skillshare/                     # Skill source of truth (managed by skillshare)
│   └── skills/                      # 29 skills deployed to ~/.claude/skills/ by bootstrap
├── tests/                           # Test suites
│   ├── python/                      # pytest tests for parallel_agent and agents/
│   └── bats/                        # Bats shell tests for bootstrap and scripts
└── docs/
    ├── README.md                    # Documentation hub
    ├── GETTING_STARTED.md           # First-time setup walkthrough
    ├── CONFIGURATION.md             # Complete config reference
    ├── ARCHITECTURE_DIAGRAMS.md     # Mermaid system diagrams (14 diagrams)
    ├── TROUBLESHOOTING.md           # Common issues and solutions
    └── COMMANDS.md                  # Command reference
```

---

## Configuration

### Enable/Disable Services

```bash
# Reconfigure after initial setup
./bootstrap.sh --reconfigure --disable-cursor
./bootstrap.sh --reconfigure --enable-gemini --disable-claude
./bootstrap.sh --reconfigure --disable-codex

# Enable Git CLIs explicitly
./bootstrap.sh --reconfigure --enable-gh --enable-glab

# Configure MCP servers (interactive per-server selection; --force to auto-accept all)
./bootstrap.sh --install-mcp
```

### Model Selection

```bash
# Use advanced models for security analysis
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Use lightweight models for quick queries
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  "Quick question"
```

**See**: [Configuration Guide](docs/CONFIGURATION.md) for complete YAML reference, environment variables, and advanced options

---

## Troubleshooting

**Bootstrap fails with "Permission denied":**

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

**Agents not running:**

```bash
# Check service configuration
cat ~/.claude/config/services.yml

# Verify CLI tools installed
which claude gemini cursor codex
```

**Codex fails with session permission errors:**

```bash
# Symptom from parallel_agent.py/check_status.sh:
# "Codex session storage not writable: ~/.manifest/codex/sessions"

# Preferred fix (restore ownership/permissions)
sudo chown -R "$(whoami)" ~/.manifest
chmod -R u+rwX ~/.manifest
```

```bash
# Optional override: move Codex state to a custom path
mkdir -p ~/.manifest/custom-codex-state
export CODEX_HOME="$HOME/.manifest/custom-codex-state"

# Then run orchestration as normal
~/.claude/scripts/parallel_agent.py --codex-only --codex-model advanced "Quick test"
```

**See**: [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for 15+ common issues with solutions

---

## Testing

```bash
# Python tests (128 tests covering agents/ package and parallel_agent.py)
pytest tests/python/ -q

# Shell tests (117 Bats tests covering bootstrap and scripts)
npx bats tests/bats/

# Lint shell scripts
shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh

# Validate YAML configs
yamllint configs/claude/config/*.yml
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
```

CI runs on every push via GitHub Actions (`.github/workflows/ci.yml`).

---

## License

This project is licensed under a Proprietary License - see the [LICENSE](LICENSE) file for details.

**Key Restrictions:**

- ✅ Use and modify for personal/internal purposes
- ❌ Distribution, sale, or sublicensing without written permission from ReefBytes
- ❌ Commercial use requires explicit authorization

For licensing inquiries: [ReefBytes/Manifest](https://github.com/ReefBytes/Manifest)

---

## Related Projects

- [Claude Code](https://claude.ai/code) - Official Anthropic CLI
- [Cursor](https://cursor.sh) - AI-powered IDE
- [Google Gemini CLI](https://www.npmjs.com/package/@google/gemini-cli) - Gemini command-line interface
- [OpenAI Codex CLI](https://github.com/openai/codex) - Codex terminal coding agent

---

## Support

- **Issues**: [GitHub Issues](https://github.com/ReefBytes/Manifest/issues)
- **Documentation**: [docs/](docs/)
- **AI Context**: Read [CLAUDE.md](CLAUDE.md) for Claude Code integration details
