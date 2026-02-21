# Manifest

[![Manifest CI](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml/badge.svg)](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml)

> Parallel LLM agent orchestration framework for Claude Code, Cursor IDE, Gemini
> CLI, and Codex CLI

**Last Updated**: 2026-02-11 (Python parallel agent feature parity — Codex agent,
ServiceConfig, CLI flags)

Manifest is a configuration repository that deploys a sophisticated parallel
agent orchestration system to `~/.claude/`, `~/.cursor/`, `~/.gemini/`, and
`~/.codex/`. It enables Claude Code, Cursor IDE, Gemini CLI, and Codex CLI to
share guides, skills, prompts, and scripts while leveraging multiple AI agents
for cross-verification, consensus scoring, and enhanced code analysis.

**Core Capabilities**: Multi-agent orchestration | Consensus scoring | Model
fallback | Two-tier validation | Production-grade templates

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

# Verify installation (Bash version)
~/.claude/scripts/parallel_agent.sh --json "Test connection"

# Or use Python version (Phase 3, recommended)
python3 ~/.claude/scripts/parallel_agent.py --json "Test connection"
```

⏱️ **Time to setup**: ~5 minutes | 💻 **Platforms**: macOS (Intel/Apple Silicon),
Linux (Debian, RHEL, Arch, openSUSE)
🐍 **Python**: 3.9+ (Phase 3 features require Python; bootstrap auto-detects and
prefers 3.12+)

---

## Features

- **Parallel Agent Orchestration**: Run 2-4 AI agents simultaneously
  (Cursor, Gemini, Claude, Codex) with real-time streaming display
- **Phase 3 Python Implementation** (NEW): Production-grade async agent with
  logging, validation, synthesis, and streaming
- **Comprehensive Logging**: Structured JSON logs with correlation IDs, rotation
  (10MB, 5 backups), performance metrics
- **Full Validation Engine**: Tier 1 (critical: security, errors, breaking
  changes) + Tier 2 (quality: bugs, performance, tests)
- **Automatic Synthesis**: Disagreement resolution when consensus < 50% using
  Claude Sonnet
- **Streaming Responses**: Real-time Rich Live display with progressive updates
  (4 updates/sec)
- **Consensus Scoring**: Variance-based algorithm calculates agreement (≥80% =
  high confidence, <50% = escalate + synthesis)
- **Intelligent Model Selection**: Task-based routing (security→opus/gpt-5.2,
  review→sonnet/gpt-5.1-codex, quick→haiku/mini)
- **Credit Exhaustion Fallback**: Automatic detection and retry with cheaper
  models (opus→sonnet→haiku)
- **Cross-Platform**: Native support for macOS (Intel/Apple Silicon) and 5 major
  Linux distributions
- **Unified Label Management**: Canonical label registry with sync across GitHub,
  GitLab, and Linear
- **Production Templates**: Pre-configured permission templates for Django,
  Express, Go microservices, Python monorepos

---

## Architecture

```text
User → Claude Code → /command → parallel_agent.sh / parallel_agent.py
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

**Visual Documentation**: [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md)
Mermaid flowcharts showing bootstrap, execution, validation, and consensus flows

---

## Available Commands

| Command | Description | Parallel Agents | Validation |
| :--- | :--- | :--- | :--- |
| `/project-commit` | Full commit pipeline | CONDITIONAL | Tier 1 + Tier 2 |
| `/refactor-python` | Python security analysis | ALWAYS | Tier 1 + Tier 2 (≥0.80) |
| `/refactor-shell` | Shell security checks | ALWAYS | Tier 1 + Tier 2 (≥0.70) |
| `/docs-diagrams` | Mermaid flowcharts | CONDITIONAL | Tier 2 |
| `/docs-improve` | Diataxis analysis | CONDITIONAL | Tier 2 |
| `/docs-readme` | README improvement | NEVER | Tier 2 |
| `/issue-prioritize` | Rank open issues | CONDITIONAL | Tier 2 |
| `/issue-triage` | Linear issue audit | CONDITIONAL | Tier 2 |
| `/plan-manage` | Plan lifecycle | CONDITIONAL | Tier 2 |
| `/browser-test` | Browser testing | CONDITIONAL | Tier 2 |

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

---

## Documentation

| Document | Purpose | Audience | Reading Time |
| :--- | :--- | :--- | :--- |
| [Getting Started](docs/GETTING_STARTED.md) | Setup/verification | New users | 10 min |
| [Configuration](docs/CONFIGURATION.md) | YAML reference | Operators | 15 min |
| [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) | Visual docs | Developers | 20 min |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common problems | All users | 10 min |
| [AGENTS.md](AGENTS.md) | AI agent instructions | AI assistants | 8 min |
| [CLAUDE.md](CLAUDE.md) | Claude Code context | AI assistants | 8 min |

**Full documentation index**: [docs/README.md](docs/README.md) •
**Quick ref**: [Commands](docs/COMMANDS.md)

---

## Project Structure

```text
Manifest/
├── bootstrap.sh                     # Cross-platform installation script
├── bootstrap/                       # Modular bootstrap libraries and hooks
│   ├── lib/
│   │   ├── common.sh                # Output, prompts, symlinks
│   │   ├── modules.sh               # Module loader + hooks
│   │   ├── platform.sh              # Platform detection
│   │   ├── config.sh                # Arg parsing + config helpers
│   │   ├── install.sh               # CLI installation
│   │   ├── auth.sh                  # Authentication + state
│   │   ├── deploy.sh                # Deployment/verification
│   │   └── mcp.sh                   # MCP installation
│   └── modules/README.md            # Custom bootstrap modules
├── CLAUDE.md                        # Claude Code project context
├── AGENTS.md                        # AI agent instructions
├── configs/                         # Deployment source configs
│   ├── claude/                      # → ~/.claude/
│   │   ├── CLAUDE.md                # Orchestration guide
│   │   ├── skills/                  # Shared skill library
│   │   ├── prompts/                 # Agent prompt templates
│   │   ├── config/                  # YAML configuration files
│   │   │   ├── services.yml         # Service states
│   │   │   ├── mcp_servers.yml      # MCP registry
│   │   │   ├── command_config.yml   # Tool policies
│   │   │   ├── validation_criteria.yml # Validation rules
│   │   │   └── labels.yml           # Label registry
│   │   ├── scripts/                 # Orchestration scripts
│   │   │   ├── parallel_agent.sh    # Core engine (Bash)
│   │   │   ├── parallel_agent.py    # Core engine (Python)
│   │   │   ├── git_platform.sh      # Git detection
│   │   │   ├── git_ops.sh           # Git operations
│   │   │   ├── linear_ops.sh        # Linear API wrapper
│   │   │   └── label_sync.sh        # Label provisioning
│   │   └── settings.local.json      # Default permissions
│   ├── cursor/                      # → ~/.cursor/
│   │   ├── rules/                   # Cursor rules (.mdc)
│   │   ├── mcp.json                 # Cursor MCP defaults
│   │   └── (symlinks to ../claude/) # Shared resources
│   ├── gemini/                      # → ~/.gemini/
│   │   ├── GEMINI.md                # Gemini guide
│   │   ├── settings.json            # Gemini settings
│   │   └── (symlinks to ../claude/) # Shared resources
│   └── codex/                       # → ~/.codex/
│       ├── AGENTS.md                # Codex guide
│       └── (symlinks to ../claude/) # Shared resources
├── .claude/                         # Repo-specific config
│   ├── CLAUDE.md                    # Developer guide
│   └── settings.local.json          # Repo permissions
├── templates/                       # Production templates
│   ├── settings-low-risk.json       # Low-risk permissions
│   └── permissions/
│       ├── django-web-app.json      # Django template
│       ├── express-api.json         # Express.js template
│       ├── go-microservices.json    # Go template
│       └── python-monorepo.json     # Python template
└── docs/
    ├── README.md                    # Documentation hub
    ├── GETTING_STARTED.md           # Setup walkthrough
    ├── CONFIGURATION.md             # Config reference
    ├── ARCHITECTURE_DIAGRAMS.md     # System diagrams
    ├── TROUBLESHOOTING.md           # Issues and solutions
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

# Configure MCP servers (interactive per-server selection)
./bootstrap.sh --install-mcp
```

### Model Selection

```bash
# Use advanced models for security analysis
~/.claude/scripts/parallel_agent.sh \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Use lightweight models for quick queries
~/.claude/scripts/parallel_agent.sh \
  --cursor-model mini \
  --claude-model haiku \
  "Quick question"
```

**See**: [Configuration Guide](docs/CONFIGURATION.md) for complete YAML
reference, environment variables, and advanced options

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
# Symptom from parallel_agent.sh/check_status.sh:
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
~/.claude/scripts/parallel_agent.sh --codex-only --codex-model advanced "Test"
```

**See**: [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for 15+ common issues
with solutions

---

## License

This project is licensed under a Proprietary License - see the [LICENSE](LICENSE)
file for details.

**Key Restrictions:**

- ✅ Use and modify for personal/internal purposes
- ❌ Distribution, sale, or sublicensing without written permission
- ❌ Commercial use requires explicit authorization

For licensing inquiries:
[ReefBytes/Manifest](https://github.com/ReefBytes/Manifest)

---

## Related Projects

- [Claude Code](https://claude.ai/code) - Official Anthropic CLI
- [Cursor](https://cursor.sh) - AI-powered IDE
- [Google Gemini CLI](https://www.npmjs.com/package/@google/gemini-cli)
- [OpenAI Codex CLI](https://github.com/openai/codex) - Codex terminal agent

---

## Support

- **Issues**: [GitHub Issues](https://github.com/ReefBytes/Manifest/issues)
- **Documentation**: [docs/](docs/)
- **AI Context**: Read [CLAUDE.md](CLAUDE.md) for Claude Code integration details
