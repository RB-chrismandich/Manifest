# Changelog

> Version history for the Manifest parallel agent orchestration framework

**Last Updated**: 2026-06-11

All notable changes are documented here in reverse chronological order.

---

## [Unreleased]

No unreleased changes — specs/003 shipped 2026-06-11 (see below).

---

## [2026-06]

### specs/003 — Skill Library Consolidation & Repo Health (shipped 2026-06-11, PRs #289 #291 #293 #294 #296)

- **Skill library consolidated 81 → 69** (specs/003) — six duplicate clusters
  resolved (five merged, one cross-anchored): `address-pr-comments` (absorbs 2), `session-memory-compress`
  (absorbs 1), `live-data-validation` (absorbs 3, mode subsections), new
  `verify-premise` (absorbs 5), new `retire-component-cleanup` (absorbs 3);
  `reset-reapply-clean-pr`/`clean-pr-from-stale-base` gain mutual decision
  anchors. Evolve's `{{LIBRARY}}` prompt now carries `name — description`
  lines so duplicates are suppressed at the source.
- **Prune-on-deploy** — `deploy_home_skills` prunes previously-deployed skills
  removed from the source of truth via a `.deployed-skills` manifest; skills
  added by other tools are never touched (does NOT reintroduce the PR #255
  blind `--delete` data-loss bug).
- **Docs accuracy** — command tables unified to canonical `docs/COMMANDS.md`
  (33 rows mirrored byte-identically in CLAUDE.md, AGENTS.md,
  configs/claude/CLAUDE.md); skill counts corrected to 69.
- **Tests & CI (US4)** — behavioral bats suites for learning_capture,
  check_status, generate_cursor_rules, browser_test (+ browser-use
  bootstrap toggle); CI pins matching pre-commit + dependency caching;
  cursor-rules drift check now catches untracked files.
- **Hygiene (US5)** — specs/002 marked Delivered; canonical `err()`
  convention swept across configs/claude/scripts/; `--help` on all
  user-facing scripts (+ help_coverage.bats); records/ and
  package-lock.json untracked and gitignored.

### Added

- **SkillClaw promote audit log + live status/ETA** (PR #284) — new `skillclaw_audit.py`
  writes an append-only `~/.skillclaw/promote.log` (JSONL history, self-trimmed to
  ~50 runs) and a live `status.json` snapshot. `skillclaw_promote.sh --status`
  reports where a run is and a rough ETA; the evolve stage prints per-chunk
  progress. Fail-open: audit I/O never blocks a promote run.
- **45 SkillClaw-evolved skills** (PR #285) — promoted via the proxy-free
  evolve pipeline, one commit per skill.
- **spec-review reviewer: Gemini → agy (Antigravity)** (PR #282) — seam renamed
  to `SPEC_REVIEW_CLI`, default reviewer `agy`.

### Fixed

- **label_sync.sh Bash 3.2 `set -u` crash** — empty `team_args[@]` expansion
  guarded; sync no longer aborts after the first label.
- **SkillClaw promote review fixes** (PRs #284/#285) — truthful `run_start`
  config, dropped-candidate reasons, evolve `stage_start` on empty sessions,
  ingest count in `stage_end`, `trim()` clamp.

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
