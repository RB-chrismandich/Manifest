# Manifest

> Parallel LLM agent orchestration framework for Claude Code

**Last Updated**: 2026-01-27

Manifest is a configuration repository that deploys a sophisticated parallel agent orchestration system to `~/.claude/`, enabling Claude Code to leverage multiple AI agents (Cursor, Gemini CLI, Claude CLI) for cross-verification, consensus scoring, and enhanced code analysis.

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

**Time to setup**: ~5 minutes | **Platforms**: macOS, Linux

---

## Features

- **Parallel Agent Orchestration**: Run Cursor, Gemini, and Claude agents simultaneously for diverse perspectives
- **Consensus Scoring**: Automatic agreement analysis with configurable thresholds (≥80% auto-proceed, <50% escalate)
- **Model Selection**: Task-based model routing (security → opus/advanced, quick → haiku/mini)
- **Credit Fallback**: Automatic retry with cheaper models on quota exhaustion
- **Two-Tier Validation**: Critical security checks (Tier 1) + quality metrics (Tier 2)
- **Cross-Platform**: Supports macOS (Intel/Apple Silicon) and Linux (Debian, RHEL, Arch, openSUSE)

---

## Architecture

```
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

**See**: [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) for visual documentation

---

## Available Commands

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/refactor` | Python codebase security and quality analysis | ALWAYS |
| `/shell-refactor` | Bash/Shell script security and quality analysis | ALWAYS |
| `/generate-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/improve-docs` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/improve-readme` | Improve README documentation | NO |

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

| Document | Purpose | Audience |
|----------|---------|----------|
| [Getting Started](docs/GETTING_STARTED.md) | First-time setup walkthrough | New users |
| [Configuration](docs/CONFIGURATION.md) | All configuration options | Operators |
| [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) | Visual system documentation | Developers |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common problems and solutions | All users |
| [CLAUDE.md](CLAUDE.md) | Repository context for Claude Code | AI assistants |

**Full documentation index**: [docs/README.md](docs/README.md)

---

## Project Structure

```
Manifest/
├── bootstrap.sh                     # Cross-platform installation script
├── CLAUDE.md                        # AI assistant context
├── .claude/                         # Configuration deployed to ~/.claude/
│   ├── CLAUDE.md                    # Orchestration guide
│   ├── commands/                    # Slash commands (refactor, generate-diagrams)
│   ├── skills/code-quality/         # Auto-triggered quality checks
│   ├── prompts/                     # Agent orchestration templates
│   ├── config/                      # YAML configuration files
│   │   ├── services.yml             # Agent enable/disable states
│   │   ├── command_config.yml       # Tool policies and thresholds
│   │   └── validation_criteria.yml  # Tier 1/2 validation rules
│   └── scripts/
│       └── parallel_agent.sh        # Core orchestration engine
└── docs/
    ├── README.md                    # Documentation hub
    ├── GETTING_STARTED.md           # First-time setup
    ├── CONFIGURATION.md             # Config reference
    ├── ARCHITECTURE_DIAGRAMS.md     # System diagrams
    └── TROUBLESHOOTING.md           # Common issues
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

**See**: [Configuration Guide](docs/CONFIGURATION.md) for all options

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

**See**: [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for more solutions

---

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style guidelines
- Testing requirements
- Pull request process

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

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
