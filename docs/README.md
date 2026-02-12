# Documentation Hub

> Complete documentation index for the Manifest parallel agent orchestration framework

**Last Updated**: 2026-02-11

---

## Quick Links

- **New here?** Start with [Getting Started](GETTING_STARTED.md)
- **Setting up agents?** See [Configuration](CONFIGURATION.md)
- **Having issues?** Check [Troubleshooting](TROUBLESHOOTING.md)
- **Understanding the system?** View [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md)

---

## Documentation by Audience

### For New Users

| Document | Description | Estimated Time |
|----------|-------------|----------------|
| [Getting Started](GETTING_STARTED.md) | First-time setup walkthrough | 10 minutes |
| [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) | Visual overview of the system | 5 minutes |

### For Operators

| Document | Description | Use When |
|----------|-------------|----------|
| [Configuration](CONFIGURATION.md) | All configuration options and examples | Customizing behavior |
| [Troubleshooting](TROUBLESHOOTING.md) | Common problems and solutions | Something isn't working |

### For Developers

| Document | Description | Use When |
|----------|-------------|----------|
| [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) | System design and data flows | Understanding internals |
| [CLAUDE.md](../CLAUDE.md) | Repository context and structure | Contributing code |
| [.claude/CLAUDE.md](../.claude/CLAUDE.md) | Orchestration guide (deployed version) | Deep dive into orchestration |

### For Contributors

| Document | Description | Use When |
|----------|-------------|----------|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Contribution guidelines | Before submitting PRs |
| [CHANGELOG.md](../CHANGELOG.md) | Version history | Tracking changes |

---

## All Documents

### Core Documentation

| File | Description | Last Updated | Status |
|------|-------------|--------------|--------|
| [README.md](../README.md) | Project overview and quick start | 2026-01-27 | ✅ |
| [CLAUDE.md](../CLAUDE.md) | AI assistant context for the repository | - | ⚠️ Needs update metadata |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to contribute to the project | - | 📝 To be created |
| [CHANGELOG.md](../CHANGELOG.md) | Version history and release notes | - | 📝 To be created |

### User Documentation

| File | Description | Last Updated | Status |
|------|-------------|--------------|--------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | First-time user guide | 2026-01-27 | ✅ |
| [CONFIGURATION.md](CONFIGURATION.md) | Configuration reference | 2026-01-27 | ✅ |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues and solutions | 2026-01-27 | ✅ |

### Technical Documentation

| File | Description | Last Updated | Status |
|------|-------------|--------------|--------|
| [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) | Visual system documentation | 2026-01-27 | ✅ |

### Internal Documentation

| File | Description | Purpose |
|------|-------------|---------|
| [configs/claude/CLAUDE.md](../configs/claude/CLAUDE.md) | Orchestration guide (deployed to ~/.claude/) | AI agent coordination |
| [configs/claude/skills/\*/SKILL.md](../configs/claude/skills/) | Skill definitions (slash commands) | Command behavior |
| [configs/claude/prompts/\*.md](../configs/claude/prompts/) | Agent orchestration templates | Synthesis and validation |
| [configs/claude/skills/code-quality/SKILL.md](../configs/claude/skills/code-quality/SKILL.md) | Auto-triggered code quality skill | Security/quality checks |

---

## Documentation Standards

All documentation in this repository follows these conventions:

### Required Elements

Every user-facing document MUST include:

- **Title** (H1): Clear, descriptive name
- **Tagline**: One-line description in blockquote
- **Last Updated**: Date in YYYY-MM-DD format
- **Table of Contents**: For documents >100 lines
- **Related Documents**: Links to related docs at bottom

### Code Block Standards

```yaml
# All code blocks MUST specify language
services:
  claude:
    enabled: true  # Good: syntax highlighting works
```

### Link Standards

- Use **relative paths** for internal links: `[Config](CONFIGURATION.md)` ✅
- Avoid absolute URLs for internal docs: `https://github.com/.../CONFIGURATION.md` ❌
- Include link descriptions: `[Configuration Guide](CONFIGURATION.md) - All config options` ✅

### Formatting Standards

- Use **tables** for structured comparisons
- Use **code blocks** for all commands, config snippets, file contents
- Use **blockquotes** (`>`) for important callouts
- Use **bold** for UI elements and emphasis
- Use `code` for file names, commands, config keys

---

## How to Navigate

### By Task

**I want to...**

- **Get started with Manifest** → [Getting Started](GETTING_STARTED.md)
- **Configure agent behavior** → [Configuration](CONFIGURATION.md)
- **Understand the architecture** → [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md)
- **Fix a problem** → [Troubleshooting](TROUBLESHOOTING.md)
- **Contribute code** → [CONTRIBUTING.md](../CONTRIBUTING.md)
- **See what changed** → [CHANGELOG.md](../CHANGELOG.md)

### By Role

**I am a...**

- **First-time user** → Start with [README](../README.md), then [Getting Started](GETTING_STARTED.md)
- **System operator** → Read [Configuration](CONFIGURATION.md) and [Troubleshooting](TROUBLESHOOTING.md)
- **Developer** → Review [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) and [CLAUDE.md](../CLAUDE.md)
- **Contributor** → See [CONTRIBUTING.md](../CONTRIBUTING.md)
- **AI assistant** → Read [CLAUDE.md](../CLAUDE.md) for repository context

---

## Documentation Health

**Current Score**: 52/100

**Areas for Improvement**:

- ⚠️ Missing "Last Updated" dates on 50% of core docs
- ⚠️ Limited cross-referencing between documents
- ⚠️ No CONTRIBUTING.md or CHANGELOG.md yet

**Recent Additions**:

- ✅ 2026-01-27: Added README.md
- ✅ 2026-01-27: Added GETTING_STARTED.md
- ✅ 2026-01-27: Added CONFIGURATION.md
- ✅ 2026-01-27: Added TROUBLESHOOTING.md
- ✅ 2026-01-27: Added this documentation hub

---

## Contributing to Documentation

Found a typo? Want to improve an explanation? Documentation contributions are welcome!

1. Edit the relevant `.md` file
2. Update the "Last Updated" date
3. Submit a pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.

---

## Related Resources

- **Main Repository**: [../README.md](../README.md)
- **Bootstrap Script**: [../bootstrap.sh](../bootstrap.sh)
- **Orchestration Script**: [../configs/claude/scripts/parallel_agent.sh](../configs/claude/scripts/parallel_agent.sh)
- **Configuration Files**: [../configs/claude/config/](../configs/claude/config/)
