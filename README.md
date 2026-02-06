# Manifest

> Parallel LLM agent orchestration framework for Claude Code

**Last Updated**: 2026-02-05

Manifest is a configuration repository that deploys a sophisticated parallel agent
orchestration system to `~/.claude/`, enabling Claude Code to leverage multiple AI agents
(Cursor, Gemini CLI, Claude CLI) for cross-verification, consensus scoring,
and enhanced code analysis.

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

# Verify installation
~/.claude/scripts/parallel_agent.sh --json "Test connection"
```

⏱️ **Time to setup**: ~5 minutes | 💻 **Platforms**: macOS (Intel/Apple Silicon), Linux (Debian, RHEL, Arch, openSUSE)

---

## Features

- **Parallel Agent Orchestration**: Run 2-3 AI agents simultaneously (Cursor, Gemini, Claude) with real-time monitoring
- **Consensus Scoring**: Variance-based algorithm calculates agreement (≥80% = high confidence, <50% = escalate)
- **Intelligent Model Selection**: Task-based routing (security→opus/gpt-5.2, review→sonnet/gpt-5.1-codex, quick→haiku/mini)
- **Credit Exhaustion Fallback**: Automatic detection and retry with cheaper models (opus→sonnet→haiku)
- **Two-Tier Validation**: Tier 1 (security, breaking changes) blocks commits • Tier 2 (quality) provides guidance
- **Cross-Platform**: Native support for macOS (Intel/Apple Silicon) and 5 major Linux distributions
- **Production Templates**: Pre-configured permission templates for Django, Express, Go microservices, Python monorepos

---

## Architecture

```text
User → Claude Code → /command → parallel_agent.sh
                                      ↓
                    ┌─────────────────┼─────────────────┐
                    ↓                 ↓                 ↓
              Cursor Agent      Gemini CLI       Claude CLI
              (IDE Context)   (Broad Knowledge) (Deep Reasoning)
                    ↓                 ↓                 ↓
                    └─────────────────┼─────────────────┘
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
| `/project-commit` | Full commit pipeline: regenerate docs, pull latest, run pre-commits, commit, push | CONDITIONAL (Phase 3) | Tier 1 + Tier 2 |
| `/refactor-python` | Python security, architecture, code quality analysis | ALWAYS | Tier 1 + Tier 2 (≥0.80) |
| `/refactor-shell` | Bash/Shell script security and quality with shellcheck | ALWAYS | Tier 1 + Tier 2 (≥0.70) |
| `/docs-diagrams` | Generate Mermaid architecture flowcharts and sequence diagrams | CONDITIONAL (≥5 imports) | Tier 2 |
| `/docs-improve` | Analyze docs against Diataxis framework (tutorials, how-tos, reference, explanation) | CONDITIONAL (≥500 lines) | Tier 2 |
| `/docs-readme` | Improve README structure and content following best practices | NEVER | Tier 2 |

---

## Requirements

**For bootstrap.sh (automated setup):**

- macOS 10.15+ or Linux (Debian/Ubuntu, RHEL/Fedora, Arch, openSUSE)
- Internet connection for package downloads
- npm-compatible environment (auto-installed if missing)

**For manual setup:**

- Bash 4.0+
- Node.js 18+ and npm
- One or more of: Claude CLI, Gemini CLI, Cursor Agent

---

## Documentation

| Document | Purpose | Audience | Reading Time |
|----------|---------|----------|--------------|
| [Getting Started](docs/GETTING_STARTED.md) | First-time setup walkthrough with verification steps | New users | 10 min |
| [Configuration](docs/CONFIGURATION.md) | All configuration options, YAML reference, environment variables | Operators | 15 min |
| [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) | Visual system documentation with 9 Mermaid diagrams | Developers | 20 min |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common problems, error messages, solutions | All users | 10 min |
| [CLAUDE.md](CLAUDE.md) | Repository context, testing, commands reference | AI assistants | 8 min |

**Full documentation index**: [docs/README.md](docs/README.md) • **Quick ref**: [Commands](docs/COMMANDS.md)

---

## Project Structure

```text
Manifest/
├── bootstrap.sh                     # Cross-platform installation script (macOS/Linux)
├── CLAUDE.md                        # AI assistant context
├── .claude/                         # Configuration deployed to ~/.claude/
│   ├── CLAUDE.md                    # Orchestration guide
│   ├── commands/                    # Slash commands (refactor-python, docs-diagrams, etc.)
│   ├── skills/code-quality/         # Auto-triggered quality checks
│   ├── prompts/                     # Agent orchestration templates
│   │   ├── preflight_analysis.md    # Pre-flight review criteria
│   │   ├── synthesis.md             # Agent disagreement synthesis
│   │   └── validation.md            # Validation criteria template
│   ├── config/                      # YAML configuration files
│   │   ├── services.yml             # Agent enable/disable states
│   │   ├── command_config.yml       # Tool policies, thresholds, model selection
│   │   └── validation_criteria.yml  # Tier 1/2 validation rules
│   └── scripts/
│       └── parallel_agent.sh        # Core orchestration engine (1244 lines)
├── templates/                       # Production-grade permission templates
│   ├── settings-low-risk.json       # Low-risk auto-executable permissions
│   └── permissions/
│       ├── django-web-app.json      # Django web application
│       ├── express-api.json         # Express.js API
│       ├── go-microservices.json    # Go microservices
│       └── python-monorepo.json     # Python monorepo
└── docs/
    ├── README.md                    # Documentation hub
    ├── GETTING_STARTED.md           # First-time setup walkthrough
    ├── CONFIGURATION.md             # Complete config reference
    ├── ARCHITECTURE_DIAGRAMS.md     # 9 Mermaid system diagrams
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
which claude gemini cursor
```

**See**: [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for 15+ common issues with solutions

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

---

## Support

- **Issues**: [GitHub Issues](https://github.com/ReefBytes/Manifest/issues)
- **Documentation**: [docs/](docs/)
- **AI Context**: Read [CLAUDE.md](CLAUDE.md) for Claude Code integration details
