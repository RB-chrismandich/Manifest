<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 1.1.0 (MINOR — new principle + section added; no removals/redefinitions)
Modified principles: N/A (I–V unchanged)
Added:
  - Principle VI. State-Gated Lifecycle
  - ## Development Lifecycle (9-phase → command map, gating, 4-tier hierarchy, enforcement)
  Source: specs/365-lifecycle-codification (feature 365).
Removed sections: N/A
Templates / docs requiring updates (feature 365):
  - .specify/templates/plan-template.md ⚠ Constitution Check must add lifecycle gates (T034)
  - .specify/templates/tasks-template.md ⚠ reconcile "Tests OPTIONAL" w/ per-workflow smoke coverage (T034)
  - docs/SPEC-SYSTEMS.md ⚠ describe the 9-phase state-gated lifecycle (T035)
  - .specify/templates/spec-template.md ✅ no constitution-specific mandatory sections affected
  - .specify/templates/constitution-template.md ✅ source template (not modified)
Follow-up TODOs: provider-specific specifics intentionally live in
  configs/claude/config/lifecycle_providers.yml, not the constitution (durability).
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

### VI. State-Gated Lifecycle

All feature work MUST flow, in order, through the nine-phase development lifecycle — Specify →
Clarify → Spec-Review (product) → Plan → Task Creation → Analyze → Spec-Review (technical) →
Implement → Verify task-by-task — each phase mapped to existing repository commands (see the
Development Lifecycle section). Phases MUST NOT be skipped: for autonomous/agent-driven work a
skip or a failing gate is a hard halt; for human-driven work it is an advisory warning that
proceeds only with a logged override. Backward transitions are permitted only when logged. The
Verify gate IS the smoke-test suite — a unit of work MUST NOT be marked complete while a
shipped user-facing workflow lacks a passing critical-path smoke test (missing coverage is
never a pass). Review and analysis gates reuse the verdict model in Quality Gates
(APPROVED/NEEDS_REVIEW/BLOCKED).

**Rationale**: An enforced, observable lifecycle keeps a fast-moving, multi-language,
multi-provider codebase honest — coverage grows with the product, no phase is silently
skipped, and one tested gate core governs both humans and agents.

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

## Development Lifecycle

Feature work is governed by the nine-phase state machine (Principle VI), tracked per unit of
work and anchored at the Task tier. The implementation is `configs/claude/scripts/lifecycle.sh`
(the shared, bats-tested decide/gate core) fronted by the `/lifecycle-run` skill and enforced by
the autonomous-development loop — humans and agents share one tested gate.

| # | Phase | Command(s) | Exit gate |
|---|-------|-----------|-----------|
| 1 | Specify | `/speckit-specify` | `spec.md` exists |
| 2 | Clarify | `/speckit-clarify` | clarifications resolved |
| 3 | Spec-Review (product) | `/spec-review --mode product` | `APPROVED` |
| 4 | Plan | `/speckit-plan` | `plan.md` + design artifacts |
| 5 | Task Creation | `/speckit-tasks` + `/speckit-taskstoissues` | `tasks.md` + hierarchy provisioned |
| 6 | Analyze | `/speckit-analyze` | 0 critical findings |
| 7 | Spec-Review (technical) | `/spec-review --mode technical` | `APPROVED` |
| 8 | Implement | `/speckit-implement` | per-user-facing-workflow smoke coverage |
| 9 | Verify task-by-task | `/speckit-audit-tasks` + `smoke_test.py run --tier Lite` | exit `0` |

**Gating**: hard halt for agents, advisory-with-logged-override for humans (Principle VI).
Review/analyze gates use the Quality Gates verdict model.

**Hierarchy**: work is tracked in four tiers — Initiative → Epic → Task → Sub-Task — abstracted
across GitHub, GitLab, Linear, and Jira. Phases 1–7 run once at the Task and its ancestor
tiers; phases 8–9 iterate per Sub-Task. Provider-specific tier/status mappings live in
`configs/claude/config/lifecycle_providers.yml` (Jira via the pre-authenticated Atlassian MCP),
NOT in this constitution, so the durable governance here does not churn on provider changes.

**Enforcement**: the autonomous-development loop MUST NOT merge or mark a unit of work complete
until every prior-phase gate, including the Verify smoke gate, passes; otherwise it halts and
flags for a human. Lifecycle drift (skipped phase, missing coverage, stale tracking state) is
auditable via `lifecycle.sh audit`.

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

**Version**: 1.1.0 | **Ratified**: 2026-05-31 | **Last Amended**: 2026-06-28
