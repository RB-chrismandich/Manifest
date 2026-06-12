# Documentation Hub

> Complete documentation index for the Manifest parallel agent orchestration framework

**Last Updated**: 2026-06-12

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
| [.claude/CLAUDE.md](../.claude/CLAUDE.md) | Repo developer guide (skillshare, tests, conventions) | Working inside this repo |
| [configs/claude/CLAUDE.md](../configs/claude/CLAUDE.md) | Orchestration guide (deployed to `~/.claude/`) | Deep dive into orchestration |

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
| [README.md](../README.md) | Project overview and quick start | 2026-06-12 | ✅ |
| [CLAUDE.md](../CLAUDE.md) | AI assistant context for the repository | 2026-02-11 | ✅ |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to contribute to the project | 2026-05-31 | ✅ |
| [CHANGELOG.md](../CHANGELOG.md) | Version history and release notes | 2026-05-31 | ✅ |

### User Documentation

| File | Description | Last Updated | Status |
|------|-------------|--------------|--------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | First-time user guide | 2026-06-12 | ✅ |
| [CONFIGURATION.md](CONFIGURATION.md) | Configuration reference | 2026-06-12 | ✅ |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues and solutions | 2026-06-12 | ✅ |
| [COMMANDS.md](COMMANDS.md) | Built-in commands and how to build custom ones | 2026-06-10 | ✅ |

### Technical Documentation

| File | Description | Last Updated | Status |
|------|-------------|--------------|--------|
| [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) | Visual system documentation | 2026-06-12 | ✅ |
| [SKILLCLAW.md](SKILLCLAW.md) | SkillClaw session-capture and skill-evolution guide | 2026-06-08 | ✅ |
| [SPEC-SYSTEMS.md](SPEC-SYSTEMS.md) | Map of the four spec/plan systems and when to use each | 2026-06-10 | ✅ |
| [METRICS.md](METRICS.md) | Agent performance dashboard template (`/dashboard`) | 2026-02-11 | ✅ |
| [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md) | Auto-generated captured learnings (`learning_capture.sh sync-docs`) | 2026-02-13 | ✅ |
| [PRE_COMMIT.md](PRE_COMMIT.md) | Pre-commit hook reference | 2026-02-05 | ✅ |

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

**Current Score**: 90/100

**Areas for Improvement**:

- No outstanding issues — the items previously tracked here (stale user-doc dates,
  broken `docs/templates/` relative links, and missing `/skill-evolve` / `/pass-cli`
  in `docs/COMMANDS.md`) were all resolved on 2026-06-08.

**Recent Additions**:

- ✅ 2026-06-12: Documented the OAuth CLI fallback (SDK vs CLI backend selection for
  Claude/Gemini), `MODEL_CHECK_PROBE=1` live model-pin verification, and the honest
  `check_status.sh` pin summary — README, architecture diagrams,
  CONFIGURATION/GETTING_STARTED/TROUBLESHOOTING; fixed stale deploy paths
  (`.claude/` → `configs/claude/`) and output paths (`~/.claude/.agent_outputs/`)
- ✅ 2026-06-08: Documentation refresh for SkillClaw + `/pass-cli` — README, architecture
  diagrams, CONFIGURATION/TROUBLESHOOTING sections, and a Diataxis cross-link audit
- ✅ 2026-06-07: Added SKILLCLAW.md — SkillClaw passive-ingest transcript reader and skill evolution guide
- ✅ 2026-06-07: Added `/skill-evolve` skill (promote SkillClaw sessions into review PRs)
- ✅ 2026-06-07: Added `/pass-cli` skill (Proton Pass credential retrieval)
- ✅ 2026-06-07: Updated ARCHITECTURE_DIAGRAMS.md with SkillClaw pipeline diagram
- ✅ 2026-05-31: Added CONTRIBUTING.md and CHANGELOG.md
- ✅ 2026-05-31: Added `sync-skills` CLI to COMMANDS.md
- ✅ 2026-05-01: Modularized `parallel_agent.py` into `agents/` package (#260)
- ✅ 2026-01-27: Added README.md, GETTING_STARTED.md, CONFIGURATION.md, TROUBLESHOOTING.md

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
- **Orchestration Script**: [../configs/claude/scripts/parallel_agent.py](../configs/claude/scripts/parallel_agent.py)
- **Configuration Files**: [../configs/claude/config/](../configs/claude/config/)
