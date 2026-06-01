<!--
SYNC IMPACT REPORT
==================
Version change: template → 1.0.0
Modified principles: N/A (initial ratification — all principles are new)
Added sections:
  - Core Principles (5 principles)
  - Quality Gates
  - Development Workflow
  - Governance
Removed sections: N/A (template placeholders cleared)
Templates requiring updates:
  - .specify/templates/plan-template.md ✅ Constitution Check section already generically aligned
  - .specify/templates/spec-template.md ✅ No constitution-specific mandatory sections affected
  - .specify/templates/tasks-template.md ✅ Test-optional stance aligns with Tier 2 advisory gate
  - .specify/templates/constitution-template.md ✅ Source template (not modified)
Follow-up TODOs: None — all placeholders resolved.
-->

# Manifest Constitution

## Core Principles

### I. Configuration-as-Code

All agent configurations, skills, orchestration rules, and prompt templates MUST be
version-controlled in `configs/` and deployed reproducibly via `bootstrap.sh`. Manual
edits to deployed files in `~/.claude/`, `~/.cursor/`, `~/.gemini/`, or `~/.codex/` are
prohibited; the repository is the authoritative source of truth. Configuration drift MUST
be detected and corrected via `./bootstrap.sh --reconfigure`.

**Rationale**: Reproducible deployments prevent environment-specific failures and ensure
every contributor operates from a consistent, auditable baseline regardless of machine
state.

### II. Parallel Agent Orchestration

Security-sensitive code changes (authentication, cryptography, secrets handling, input
validation), architectural decisions, and modifications exceeding 200 lines MUST be
cross-verified by two or more parallel agents before merge. Single-agent review is
insufficient for Tier 1 concerns. `parallel_agent.py` is the canonical tool for
orchestrating multi-agent validation; ad-hoc single-model reviews do not satisfy this
gate.

**Rationale**: Cross-verification surfaces blind spots that a single model misses;
consensus scoring provides a quantified confidence signal for human escalation decisions.

### III. Consensus-Driven Decisions

All parallel agent outputs MUST be evaluated against defined thresholds:

- ≥80% agreement → auto-proceed (high confidence)
- 50–79% agreement → surface disagreements for human review (medium confidence)
- <50% agreement → block and trigger synthesis via Claude Sonnet (low confidence)

Automated gate decisions MUST reference these thresholds. Bypassing consensus scoring
requires documented justification in the PR description.

**Rationale**: Quantified consensus prevents false confidence while reducing unnecessary
human escalation for routine, low-risk changes.

### IV. Skill-First Extensibility

New capabilities MUST be implemented as discrete, self-contained skills in
`.skillshare/skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter.
Skills MUST be independently invocable via `/skill-name` in Claude Code. Expanding
`parallel_agent.py` or other core scripts to absorb new behaviors is prohibited when a
skill is sufficient.

**Rationale**: Composable skills enable independent testing, per-platform deployment, and
targeted updates without risk to the core orchestration engine.

### V. Bootstrap Reproducibility

`bootstrap.sh` MUST produce identical deployments regardless of starting machine state.
All installation and configuration steps MUST be idempotent. Non-idempotent operations
(e.g., `git init`, credential writes) MUST be guarded by existence checks. The script
MUST exit non-zero on any unrecoverable failure rather than continuing in a degraded
state.

**Rationale**: Idempotent bootstrapping is the contract that makes this repository a
reliable configuration distribution mechanism across diverse machines and contributors.

## Quality Gates

All pull requests are subject to a two-tier validation process enforced via parallel
agent review:

**Tier 1 — Blocking (all must pass)**:
- Cross-verification: multiple agents agree on key findings
- Security: no injection, XSS, auth bypass, or secrets exposure
- Error handling: proper exceptions with no silent failures
- Breaking changes: API compatibility and data migration safety verified

**Tier 2 — Advisory (score ≥0.60 required for APPROVED verdict)**:
- Bug detection: logic errors, off-by-one, null references
- Performance: no O(n²) loops or memory leaks in hot paths
- Maintainability: clear naming, reasonable cyclomatic complexity
- Test coverage: changes include corresponding tests

**Verdicts**:
- `APPROVED`: Tier 1 passes AND Tier 2 score ≥ 0.60
- `NEEDS_REVIEW`: Tier 1 passes AND Tier 2 score < 0.60
- `BLOCKED`: Any Tier 1 check fails

## Development Workflow

**Testing**: All shell changes MUST pass `bats tests/bats/`. All Python changes MUST pass
`pytest tests/python/`. Lint with `shellcheck` (shell scripts) and `yamllint` (YAML
configs) before opening a PR.

**Skills**: New skills are added to `.skillshare/skills/` (source of truth). The path
`configs/claude/skills/` is a backward-compatibility symlink and MUST NOT be replaced
with a real directory. Home deployment (`~/.claude/skills`) is managed by `bootstrap.sh`;
skillshare manages project-scoped targets (`.github/skills`).

**Plans**: Implementation plans live in `configs/claude/.plans/` as
`YYYYMMDD-description.md`. Plans follow the lifecycle CREATE → ACTIVE → COMPLETED
(`.archive/`) or ABANDONED (`.abandoned/`). Plans untouched for 7+ days MUST be reviewed
and either updated, completed, or abandoned.

**PRs**: Each PR MUST include a constitution compliance check for Tier 1 gates.
Complexity violations introduced by the PR MUST be justified in the plan's Complexity
Tracking table. Use `/plan-manage` for orchestrated plan creation and review.

## Governance

This constitution supersedes all other development guidelines for the Manifest
repository. Conflicts between this document and README, CLAUDE.md, or other guides are
resolved in favor of the constitution.

**Amendment procedure**: Amendments require a PR with documented rationale, a semantic
version bump per the policy below, and review by at least one repository maintainer.
`LAST_AMENDED_DATE` MUST be updated to the merge date.

**Versioning policy**:
- MAJOR: backward-incompatible governance changes — principle removals or redefinitions
- MINOR: new principle or section added, or materially expanded guidance
- PATCH: clarifications, wording fixes, non-semantic refinements

**Compliance review**: All PRs MUST verify adherence to Tier 1 quality gates. Annual
review of all principles is RECOMMENDED to ensure alignment with project evolution.

**Runtime guidance**: Use `configs/claude/CLAUDE.md` for session-level development
guidance; it is the deployed document that governs active Claude Code sessions.

**Version**: 1.0.0 | **Ratified**: 2026-05-31 | **Last Amended**: 2026-05-31
