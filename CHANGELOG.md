# Changelog

> Version history for the Manifest parallel agent orchestration framework

**Last Updated**: 2026-05-31

All notable changes are documented here in reverse chronological order.

---

## [Unreleased]

## [2026-05]

### Added
- **`agents/` package** (PR #260) — `parallel_agent.py` modularized into a proper Python package:
  `agents/cli.py`, `config.py`, `orchestrator.py`, `runners.py`, `synthesis.py`, `validation.py`
- **`sync-skills` CLI command** (PR #258) — native binary at `~/.local/bin/sync-skills` for daily
  skill development; deploys `.skillshare/skills/` to all home targets with `MANIFEST_ROOT` support
- **CI drift guard** (PR #259) — detects stale cursor rules and config drift in CI
- **speckit integration** — spec/plan/task workflow tooling initialized

### Changed
- **Skillshare centralization** (PR #255) — `.skillshare/skills/` is now the source of truth;
  `configs/claude/skills/` is a compatibility symlink; bootstrap uses additive rsync (no `--delete`)
- **CLAUDE.md tiered** (PR #255) — core guide + reference index pattern adopted

### Removed
- **`parallel_agent.sh`** (PR #257) — retired in favor of `parallel_agent.py`; all 56+ call sites
  updated; -1939 lines

### Fixed
- **rsync `--delete` data-loss bug** (PR #255) — removed `--delete` from skill deploy to prevent
  wiping home skills on bootstrap

---

## [2026-02]

### Added
- **Codex CLI support** — fourth agent alongside Cursor, Gemini, Claude
- **Python parallel agent** (PR #49) — feature parity with shell script: async orchestration,
  structured JSON logging, Tier 1/2 validation engine, consensus scoring, Rich streaming display
- **`browser-test` skill** — AI-powered E2E testing via browser-use YAML prompts
- **GitLab CI** and multi-language prompt templates

### Fixed
- Command injection in `CursorAgent` (CWE-78)
- `git_ops.sh` GitLab flag translation for `pr-create`
- MCP re-registration guard (skip when already configured)

---

## [2026-01]

### Added
- Unified label management across GitHub, GitLab, and Linear (`labels.yml`, `label_sync.sh`)
- `issue-prioritize` and `issue-triage` commands with Linear integration
- Bootstrap modularization (`bootstrap/lib/`) with hookable module system
- Production-grade permission templates (Django, Express, Go microservices, Python monorepo)
- `docs/` documentation hub with Getting Started, Configuration, Troubleshooting, Architecture

### Changed
- Deployment configs moved to `configs/` to prevent session config override

---

## Related Documents

- [README.md](README.md) — Project overview
- [docs/README.md](docs/README.md) — Documentation hub
