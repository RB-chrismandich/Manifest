# Knowledge Base — Captured Learnings & Best Practices

> A living document of patterns, antipatterns, tool discoveries, and configuration
> insights captured during development with the Manifest orchestration framework.

**Last Updated**: 2026-02-11
**Source**: `.claude/config/knowledge_base.yml` (machine-readable), this file (human-readable)
**Managed by**: `learning-loop` skill, `antipattern-detect` skill

---

## Overview

This knowledge base serves as the human-readable companion to
`.claude/config/knowledge_base.yml` (the machine-readable source of truth).
Entries are captured automatically by the `learning-loop` skill and analyzed by the
`antipattern-detect` skill. Both skills write structured records to the YAML config
and surface summaries here for team reference.

## How to Contribute

| Action | Command | Description |
|--------|---------|-------------|
| Capture a new learning | `/learning-loop` | Records a pattern, tool discovery, or config insight |
| Detect antipatterns | `/antipattern-detect` | Analyzes recent code for known antipatterns |
| Manual entry | Edit this file + `knowledge_base.yml` | Add both human-readable and machine-readable records |

When adding entries manually, ensure both this document **and**
`.claude/config/knowledge_base.yml` are updated to stay in sync.

### Categories

| Category | Description | Example |
|----------|-------------|---------|
| Pattern | Recommended coding patterns | "Use ruff instead of flake8+black+isort" |
| Antipattern | Detected issues to avoid | "Bare except clauses hide real errors" |
| Tool Discovery | New/better tooling | "golangci-lint replaces individual Go linters" |
| Config Insight | Configuration tips | "ESLint flat config requires eslint.config.js" |

### Confidence Levels

- **High**: Confirmed across multiple occurrences or from authoritative sources
- **Medium**: Observed once with strong evidence
- **Low**: Preliminary observation, needs more data

---

## Patterns

Recommended patterns discovered through development and cross-agent consensus.

| ID | Language | Title | Category | Description |
|----|----------|-------|----------|-------------|
| | | | | |

---

## Antipatterns

Detected antipatterns that should be avoided. Each entry includes the context in
which it was found and the recommended alternative.

| ID | Language | Title | Category | Description | Alternative |
|----|----------|-------|----------|-------------|-------------|
| | | | | | |

---

## Tool Discoveries

New or better tooling identified during development.

| ID | Tool | Replaces | Category | Description |
|----|------|----------|----------|-------------|
| TD-001 | ruff | flake8, isort, pycodestyle | python-linting | Ruff is a single, fast Rust-based linter and formatter that replaces flake8, isort, pycodestyle, and several other Python tools. Significantly faster and supports auto-fix for most rules. |

---

## Configuration Insights

Lessons learned about configuration, thresholds, and environment setup.

| ID | Area | Title | Description |
|----|------|-------|-------------|
| | | | |

---

## References

- **Machine-readable source**: [`.claude/config/knowledge_base.yml`](../.claude/config/knowledge_base.yml)
- **Learning loop skill**: [`.claude/skills/learning-loop/`](../.claude/skills/learning-loop/)
- **Antipattern detection skill**: [`.claude/skills/antipattern-detect/`](../.claude/skills/antipattern-detect/)
- **Metrics dashboard**: [METRICS.md](METRICS.md)
- **Orchestration guide**: [`.claude/CLAUDE.md`](../.claude/CLAUDE.md)
