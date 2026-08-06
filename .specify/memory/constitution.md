<!--
SYNC IMPACT REPORT
==================
Version change: 2.0.0 → 3.0.0 (MAJOR — Principle V.4 redefined, V.5 scoped)
Modified principles:
  - V.4 User-edit preservation → User-edit DETECTION. REDEFINED. The v2.0.0 wording
    required a modified deployed file be "preserved and reported". Feature 522 measured
    that a package-manager deployer performs the write itself, so preservation is not
    expressible by the repository — only detection is. A MUST that no capable mechanism
    can satisfy is decorative; it was violated by construction the moment the deployer
    changed. Now: detect and report, with deployed trees explicitly build outputs.
  - V.3 Orphan removal — SCOPED (not weakened) to paths a mechanism claims ownership of.
    Executables installed onto PATH with relative siblings have no ownership-tracking
    deployer, so a reconciliation pass remains necessary for them and must be recorded.
  Source: specs/522-apm-deploy-migration (feature 522), T035.
Added: N/A
Removed sections: N/A
Consequence: FR-034's build-output semantics are now constitutionally grounded rather
than in conflict. The detection half is a live obligation — see
configs/claude/scripts/apm_drift_report.sh.
-->

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

--------------------------------------------------------------------------------

Version change: 1.1.0 → 1.1.1 (PATCH — reference correction, no principle/section
  changes)
Modified principles: N/A (I–VI unchanged)
Modified sections:
  - ## Development Lifecycle: provider-specific tier/status mapping file re-pointed
    from `configs/claude/config/lifecycle_providers.yml` to
    `configs/claude/config/tracker_providers.yml`.
  Source: `lifecycle_providers.yml` was deleted (commit a0070d0) and its content
  absorbed byte-identically into `tracker_providers.yml`, part of the broader
  tracker-provider abstraction work
  (docs/superpowers/plans/2026-07-16-agent-app-agnostic-skills.md).
Removed sections: N/A
Templates / docs requiring updates: N/A (path-only correction; no template impact)
Follow-up TODOs: N/A

--------------------------------------------------------------------------------

Version change: 1.1.1 → 2.0.0 (MAJOR — two principles redefined + one added)
Modified principles:
  - I. Configuration-as-Code — REDEFINED. Was mechanism-named (`configs/` deployed
    "via bootstrap.sh"; drift corrected "via ./bootstrap.sh --reconfigure"). Now
    property-first: version-controlled source, reproducible-from-manifest deploy,
    single-owner paths, detectable+correctable drift. The named-implementation
    clause was the defect: any change of deployer contradicted the constitution
    by construction.
  - V. Bootstrap Reproducibility → V. Reproducible, Idempotent Deployment.
    REDEFINED and widened from one script to every deploy mechanism; adds
    byte-identical no-change re-runs, orphan removal, user-edit preservation,
    and disjoint path ownership as constitutional properties.
Added:
  - Principle VII. Published Artifact Integrity — governs distribution of Manifest
    configuration as published, installable packages (version pinning, lockfile
    reproducibility, integrity verification, pre-publish scrubbing, offline path).
  Source: specs/522-apm-deploy-migration (feature 522).
Modified sections:
  - ## Development Workflow → Skills: home deployment is no longer asserted to be
    `bootstrap.sh`-managed; it is now whichever mechanism owns that path, per
    Principle V's ownership rule.
Removed sections: N/A
NOTE ON SEQUENCING: this amendment is deliberately MECHANISM-NEUTRAL. It names no
  package manager and presupposes no outcome of feature 522's feasibility spike.
  It is therefore valid whether that spike returns GO or NO-GO, and it does not
  constitute adoption of any specific tool.
Templates / docs requiring updates:
  - .specify/templates/plan-template.md ⚠ Constitution Check should reference the
    ownership/idempotence gates (Principle V) for any feature touching deployment
  - CLAUDE.md / configs/claude/CLAUDE.md ⚠ drift-correction guidance still names
    `./bootstrap.sh --reconfigure`; update when a migrated domain exists
  - docs/CONFIGURATION.md, docs/GETTING_STARTED.md ⚠ same
Follow-up TODOs: Principle VII takes effect for any published package; until one is
  published it constrains nothing and is dormant by design.
-->

# Manifest Constitution

## Core Principles

### I. Configuration-as-Code

All agent configurations, skills, orchestration rules, and prompt templates MUST be
version-controlled; the repository is the authoritative source of truth and a deployed
tree is an output, never an input. Specifically:

- Every deployed artifact MUST be reproducible from committed sources plus a committed
  manifest, on a machine with no prior state.
- Manual edits to deployed files in `~/.claude/`, `~/.cursor/`, `~/.gemini/`,
  `~/.codex/`, or `~/.antigravity/` are prohibited. A mechanism that *preserves* a
  user's manual edit MUST surface it as drift rather than silently accepting it.
- Configuration drift MUST be **detectable by a command** and **correctable without
  manual reconciliation**. The correcting mechanism is whichever one owns the path
  (Principle V); this constitution does not name it.

**Rationale**: Reproducible deployments prevent environment-specific failures and ensure
every contributor operates from a consistent, auditable baseline regardless of machine
state. This principle is stated as *properties*, not as a named script: a governance rule
that hardcodes its own implementation is contradicted by any improvement to that
implementation, which converts routine engineering into a constitutional violation.

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
`.retired skill supply/skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter.
Skills MUST be independently invocable via `/skill-name` in Claude Code. Expanding
`parallel_agent.py` or other core scripts to absorb new behaviors is prohibited when a
skill is sufficient.

**Rationale**: Composable skills enable independent testing, per-platform deployment, and
targeted updates without risk to the core orchestration engine.

### V. Reproducible, Idempotent Deployment

Every mechanism that writes into an assistant home — the bootstrap installer, a package
manager, or any successor — MUST satisfy all of the following. These are properties of
*deployment*, not of any one script:

1. **Identical output**: the same sources produce the same deployed tree regardless of
   starting machine state.
2. **Idempotence**: re-running with unchanged sources produces a byte-identical tree and
   reports no changes. Non-idempotent operations (e.g. `git init`, credential writes)
   MUST be guarded by existence checks.
3. **Orphan removal**: a file a previous deploy wrote and the current sources no longer
   produce MUST be removed by the deploy itself, not by a separate reconciliation pass.
   This applies to every path a mechanism claims ownership of. A domain a mechanism does
   NOT claim — because no ownership-tracking deployer exists for it yet — is out of scope
   for this property, and its reliance on a reconciliation pass MUST be recorded rather
   than left implicit. *(Scoped v3.0.0: feature 522 established that executables installed
   onto `PATH` with relative siblings have no ownership-tracking deployer, so
   `deploy_reconcile.sh` remains necessary for them; see
   specs/522-apm-deploy-migration/migration-inventory.md.)*
4. **User-edit detection**: a deployed file the user has modified MUST NOT be *silently*
   overwritten — the modification MUST be detected and reported. Preservation is NOT
   required: deployed trees are build outputs, reproducible from versioned source, and a
   mechanism MAY overwrite a modified file provided it says so. Source is the editable
   surface; the deployed tree is not (see Principle I).

   *Amended v3.0.0. The prior wording required the file be "preserved and reported".
   Feature 522 measured that a package-manager deployer performs the write itself, so
   preservation is not expressible by the repository at all — only detection is. Requiring
   an unachievable property does not protect users; it guarantees the constitution is
   violated by every mechanism that can actually do the job, which is how a MUST becomes
   decorative. Installers that store user state MUST therefore write source or a
   user-scope file no package owns, never a deployed copy.*
5. **Single ownership**: each deployed path MUST have **exactly one** owning mechanism.
   Two mechanisms writing the same path is a defect, not an acceptable intermediate
   state, including during a migration between mechanisms.
6. **Fail closed**: exit non-zero on any unrecoverable failure rather than continuing in
   a degraded state. A step that is skipped or cannot be verified MUST NOT report success.

**Rationale**: Idempotent, self-cleaning, single-owner deployment is the contract that
makes this repository a reliable configuration distribution mechanism across diverse
machines and contributors. Properties 3–5 are stated explicitly because their absence —
not their violation — was the root cause of recurring drift: a deployer that keeps no
record of what it owns cannot remove what it orphaned, cannot tell a user's edit from its
own output, and cannot detect that a second mechanism is fighting it for the same file.

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

### VII. Published Artifact Integrity

When Manifest configuration is distributed as a **published, installable package** rather
than consumed from a local checkout, the act of publishing is outward-facing and
effectively irreversible — a published version can be superseded but not unseen. Therefore:

1. **Provenance**: a published artifact MUST be built from committed sources at a tagged
   version. Publishing from a dirty or unreproducible working tree is prohibited.
2. **Pinning**: consumed packages and the publishing/installing toolchain itself MUST be
   version-pinned and resolvable from a committed lockfile. Upgrades are deliberate
   changes that MUST re-run the deployment property checks in Principle V.
3. **Integrity**: installation MUST verify artifact integrity (hash or signature). An
   installer that cannot verify what it fetched MUST fail closed, not warn and proceed.
4. **Pre-publish scrubbing**: content MUST be scanned for secrets, credentials,
   machine-local paths, and private or user-identifying material **before** publication,
   and the scan MUST block on findings. Publishing distributes content beyond the
   maintainer's control; a post-publish discovery is not remediable by deletion.
5. **Availability independence**: a documented path MUST exist to install from a pinned
   local artifact without network or registry access, so an outage or a removed upstream
   cannot prevent a machine from being provisioned.
6. **Local development path**: contributors MUST be able to build, deploy, and test
   changes locally **without publishing**. A workflow in which every edit requires a
   publish to be testable is prohibited, as it converts iteration into distribution.

**Rationale**: Publishing converts an internal deployment concern into a supply chain.
Configuration published this way carries hooks and MCP server definitions, which are
executable code paths, not inert files — so the integrity of a published artifact is a
security property, not a packaging convenience. This principle is dormant until a package
is actually published, and constrains nothing before then.

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
| 9 | Verify task-by-task | `/spec-audit-tasks` + `smoke_test.py run --tier Lite` | exit `0` |

**Gating**: hard halt for agents, advisory-with-logged-override for humans (Principle VI).
Review/analyze gates use the Quality Gates verdict model.

**Hierarchy**: work is tracked in four tiers — Initiative → Epic → Task → Sub-Task — abstracted
across GitHub, GitLab, Linear, and Jira. Phases 1–7 run once at the Task and its ancestor
tiers; phases 8–9 iterate per Sub-Task. Provider-specific tier/status mappings live in
`configs/claude/config/tracker_providers.yml` (Jira via the pre-authenticated Atlassian MCP),
NOT in this constitution, so the durable governance here does not churn on provider changes.

**Enforcement**: the autonomous-development loop MUST NOT merge or mark a unit of work complete
until every prior-phase gate, including the Verify smoke gate, passes; otherwise it halts and
flags for a human. Lifecycle drift (skipped phase, missing coverage, stale tracking state) is
auditable via `lifecycle.sh audit`.

## Development Workflow

**Testing**: All shell changes MUST pass `bats tests/bats/`. All Python changes MUST pass
`pytest tests/python/`. Lint with `shellcheck` (shell scripts) and `yamllint` (YAML
configs) before opening a PR.

**Skills**: New skills are added to `.retired skill supply/skills/` (source of truth). The path
`configs/claude/skills/` is a backward-compatibility symlink and MUST NOT be replaced
with a real directory. Home deployment (`~/.claude/skills`) is managed by whichever
mechanism owns that path under Principle V — exactly one at any time — and retired skill supply
manages project-scoped targets (`.github/skills`).

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

**Version**: 3.0.0 | **Ratified**: 2026-05-31 | **Last Amended**: 2026-07-27
