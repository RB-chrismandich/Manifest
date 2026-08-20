# Manifest

[![Manifest CI](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml/badge.svg)](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml)

> Parallel LLM agent orchestration framework for Claude Code, Cursor IDE, Gemini CLI,
> Codex CLI, Antigravity IDE, and the Devin CLI

**Last Updated**: 2026-06-21

Manifest is a configuration repository that deploys a sophisticated parallel agent
orchestration system to `~/.claude/`, `~/.cursor/`, `~/.gemini/`, `~/.codex/`, and
`~/.antigravity/`, enabling Claude Code, Cursor IDE, Gemini CLI, Codex CLI, Antigravity
IDE, and the Devin CLI (which reads `~/.claude` in place, see below) to share guides,
skills, prompts, and scripts while leveraging multiple AI agents for cross-verification,
consensus scoring, and enhanced code analysis.

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

> **`./bootstrap.sh` is not side-effect-free on the working tree.** Every run
> no longer invokes retired skill supply (removed 2026-07-27, feature 522 FR-021a).
> The project-scoped Copilot target `.github/skills/` is no longer synced.
> to own, so the write is expected — but do not run bootstrap expecting a clean
> `git status`, and do not commit `.github/skills/`.

⏱️ **Time to setup**: ~5 minutes | 💻 **Platforms**: macOS (Intel/Apple Silicon), Linux (Debian, RHEL, Arch, openSUSE)
🐍 **Python**: 3.9+ (Phase 3 features require Python; bootstrap auto-detects and prefers 3.12+)

---

## Architecture

```text
User → Claude Code → /command → parallel_agent.py
                                          ↓
      ┌──────────┬──────────┬──────────┼──────────┬──────────┐
      ↓          ↓          ↓          ↓          ↓          ↓
Cursor Agent Gemini CLI Claude CLI Codex CLI  Antigravity  Devin
(IDE Context)(Broad     (Deep      (Terminal  (agy)        (opt-in)
             Knowledge) Reasoning)  Coding)
      ↓          ↓          ↓          ↓          ↓          ↓
      └──────────┴──────────┴──────────┼──────────┴──────────┘
                                          ↓
                              Synthesis & Validation
                                          ↓
                                      JSON Output
```

**Visual Documentation**: [Architecture Diagrams](docs/diagrams/README.md) -
Mermaid flowcharts showing bootstrap, execution, validation, and consensus flows

---

## Documentation

| Page | Answers |
|------|---------|
| [Getting Started](docs/GETTING_STARTED.md) | How do I install it and make the first run work? |
| [Features](docs/FEATURES.md) | What does Manifest actually do? |
| [Requirements](docs/getting-started/requirements.md) | What platforms and CLI versions are supported? |
| [Commands](docs/COMMANDS.md) | What can I invoke, and how do I write my own? |
| [Configuration](docs/configuration/README.md) | Which setting lives in which file? |
| [Troubleshooting](docs/troubleshooting/README.md) | Something broke — where do I look? |
| [Architecture Diagrams](docs/diagrams/README.md) | How do the pieces fit together? |
| [Project Structure](docs/PROJECT_STRUCTURE.md) | Where does everything live in this repo? |
| [Testing](docs/TESTING.md) | How do I run the test suites? |
| [Model Policy](docs/MODEL-POLICY.md) | Which model runs a session, sub-agent, or turn? |
| [Full docs index](docs/README.md) | Everything else. |

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
