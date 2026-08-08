# Phase 0 Research: Codified State-Gated Development Lifecycle

**Feature**: 365-lifecycle-codification | **Date**: 2026-06-28
**Method**: 7 parallel research agents, each grounded in repo files + targeted external research (run `wf_59c2f036-5cc`).

This document resolves every NEEDS-CLARIFICATION / open technical decision from the spec (including the two items `/speckit-clarify` deferred: state-store location and Jira access shape). Each decision is stated as Decision / Rationale / Alternatives rejected.

---

## D1. Orchestrator form factor & implementation language

**Decision**: Build a **shared Bash state-machine script** `configs/claude/scripts/lifecycle.sh`, split into:
- a **pure decision core** — `lifecycle.sh decide <signals-json>` → `{action: allow|warn|refuse, missing_prereq, reason}`, always exits 0, fails **closed** (malformed input → refuse), bats-testable offline; and
- **thin stateful subcommands** — `init`, `status`, `advance`, `anchor`, `regress` — that persist per-track JSON state.

Front it with a thin **`/lifecycle` skill** (`.retired skill supply/skills/lifecycle/SKILL.md`) for human/agent invocation, and have the **autodev loop** (`auto_issue_dev.sh` / `pr_merge_loop.sh`) consume the **same** `decide`/`advance` core for hard enforcement. Language: **Bash with embedded `python3 -c` heredocs** for JSON/decision logic. Python is reserved for the smoke **runtime**, which Verify consumes via its CLI and never re-implements.

**Rationale**: One-for-one mirror of the repo's existing state-gated automation: specs 360 (`verification_gate.sh`) and 361 (`merge_decision.sh` + `pr_merge_loop.sh` + `loop_lock.sh`) both split a pure, bats-tested `decide` core (embedded `python3 -c`, always exit 0, fail-closed) from a side-effecting shell orchestrator behind injectable seams, wrapped by a skill. 365's gating is the same shape of safety decision (FR-004 hard-refuse for agents; SC-002). A **shared** core is mandatory because the `/lifecycle` skill drives human work (advisory gating) while the autodev loop drives agent work (hard halt) — FR-004/SC-002 require both strictness modes to derive from one tested source of truth. Constitution Principle IV (Skill-First) is satisfied the way 361 satisfied it: the user-facing capability is a skill that delegates to discrete testable helpers.

**Alternatives rejected**:
- *Pure Python orchestrator* — Python here is reserved for the smoke runtime (a different concern FR-012 says to consume as-is); the orchestration layer is uniformly shell (`git_ops.sh`, `linear_ops.sh`, `verification_gate.sh`, `merge_decision.sh`).
- *Prose-only `/lifecycle` skill* — the 361 plan explicitly rejected prose because safety logic "can't be unit-tested deterministically."
- *Extend only the autodev loop* — the loop is agent-only; US1/FR-004 require humans to drive the same lifecycle under advisory gating.
- *New state-machine engine/DSL* — FR-001 forbids a parallel mechanism; phases must map to existing `/speckit-*` and `/spec-review` commands.

---

## D2. Lifecycle state store: location & schema

**Decision**: **Hybrid storage.**
- **Fine-grained per-track state** → local JSON at `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/lifecycle/state/<provider>__<sanitized-entity-id>.json`, reusing the smoke orchestrator `StateManager` persistence pattern (owner-only `0700` dir / `0600` files, atomic write, secret redaction).
- **Coarse status** (the 4 canonical statuses) → mirrored to the tracker via existing labels (`labels.yml`) so the tracker stays human-readable and the autodev loop can query it without the local store.

The local JSON is the **source of truth** for fine phase state; the tracker holds the coarse mirror (reconciled per D5).

**Rationale**: FR-003/FR-007/FR-028 need durable, inspectable, cross-session state richer than a label can hold (current_phase, completed phases, regression log, tier anchor, per-Sub-Task Implement/Verify sub-states, smoke-coverage link, exemptions). Labels alone can't carry that; a pure-tracker approach also couples every state read to a network call. The smoke `StateManager` already establishes the secure local-state idiom under a Manifest state root, so reuse keeps one convention and satisfies FR-025 (no secrets in readable form).

**Alternatives rejected**:
- *Tracker-only (labels/fields/comments)* — can't hold fine state; comment-scraping is brittle; every read is a network call.
- *Local-only (no tracker mirror)* — humans and the loop lose at-a-glance status in the tracker; breaks SC-010 reconciliation expectations.

---

## D3. Jira access shape

**Decision**: Perform Jira operations **directly via the pre-authenticated Atlassian MCP** (tools: `getJiraIssue`, `getTransitionsForJiraIssue`, `transitionJiraIssue`, `searchJiraIssuesUsingJql`, `getJiraProjectIssueTypesMetadata` / `getJiraIssueTypeMetaWithFields`, `getVisibleJiraProjects`, `createJiraIssue`, `addCommentToJiraIssue`). No bespoke auth/credential code. Route Jira through the same provider-abstraction seam as `git_ops.sh`/`linear_ops.sh` (a `jira` case in the provider dispatcher; MCP tool calls are made by the agent layer, not a REST wrapper).

**Rationale**: "Pre-authenticated MCP" is a hard spec constraint (FR-020). The Atlassian MCP server is already registered in `configs/claude/config/mcp_servers.yml` (OAuth, purpose = Jira/Confluence/Compass). It covers issue read/create, hierarchy parent linking, and the `/transitions` workflow-transition mechanism FR-021 requires (Jira status changes need transition IDs, not free-text). Going direct avoids a redundant wrapper and the credential-handling a `jira_ops.sh` REST client would imply.

**Alternatives rejected**:
- *New `jira_ops.sh` REST wrapper* — re-introduces auth/credential handling the spec forbids; duplicates what the MCP already exposes. (A thin shell shim that only *formats* MCP results could be added later if needed, but is not required.)

**Open risk**: the Atlassian MCP is registered in `mcp_servers.yml` but not yet wired into `settings.local.json` — wiring is an implementation task. Jira Initiative tier requires Advanced Roadmaps/Premium (see D4 fallback).

---

## D4. Four-tier → provider-construct mapping

**Decision**: Unifying model — **every node is an issue-like entity; every parent↔child edge is the provider's native hierarchy link**. Canonical mapping:

| Tier | Abstract | GitHub | GitLab | Linear | Jira (Cloud) |
|------|----------|--------|--------|--------|------|
| 1 | Initiative | Org-level Project V2 *(no native issue type — see fallback)* | Epic *(Premium; or top Work Item)* | Initiative | Initiative *(Advanced Roadmaps/Premium)* |
| 2 | Epic | Repo Milestone / parent Sub-Issue | Epic / parent Issue | Project | Epic |
| 3 | Task | Issue | Issue | Issue | Story / Task |
| 4 | Sub-Task | native Sub-Issue | child Issue (linked) | Sub-issue (`parentId`) | Sub-task |

**Missing/renamed-tier fallback** (FR-014): when a target instance lacks a tier (e.g., GitHub has no native Initiative type, GitLab/Jira without the Premium hierarchy), the system MUST surface a **configuration error naming the unresolved tier** and offer a declared fallback (collapse the missing tier to a label/parent-reference convention) — never a silent mismap. The tier→construct map lives in **config** (so volatile provider specifics don't churn the constitution).

**Rationale**: Satisfies FR-013 bidirectional navigation (parent↔child via each provider's native link), FR-015 artifact-at-tier, and FR-014's explicit-error requirement. Linear already implements the edge via `linear_ops.sh create-sub-issue`/`parentId`, proving the model. Keeping the table in config preserves the constitution's durability.

**Alternatives rejected**:
- *Hard-code mappings in the constitution* — volatile (provider features change); FR-017/FR-021 favor a generic representation + config reference.
- *Markdown-checklist Sub-Tasks on GitHub* — the spec/clarify settled on native Sub-Issues for symmetric, parseable hierarchy.

---

## D5. Status mapping & loop-safe reconciliation

**Decision**: A **declarative canonical-status map** + a **three-way "shadow-compare with origin suppression"** reconciliation, run inside the existing poll-based autodev loop.
- **Map**: collapse the 9 phases onto the 4 coarse canonical statuses already in `labels.yml` — `planned` (Specify–Spec-Review product), `in-progress` (Plan–Implement), `needs-review` (Verify / awaiting human), `done` (Verify passed + merged). Per-provider rendering: labels for GitHub/GitLab/Linear; **workflow transitions (by ID)** for Jira.
- **Reconcile**: each loop tick compares three values — local state, last-synced shadow, and live tracker status. If only the tracker changed → adopt it (human moved it); if only local changed → push it; if both changed since shadow → flag conflict for human. **Origin suppression**: the loop records the shadow it just wrote so its own echo is not re-processed (prevents infinite loops). All transitions idempotent.

**Rationale**: Satisfies FR-021 + SC-010 + the "tracker-originated status change" edge case without webhooks (the spec scopes webhooks out). Shadow-compare with origin suppression is the standard loop-safe reconciliation pattern and fits the existing poll loop.

**Alternatives rejected**:
- *Real-time webhook receiver* — explicitly out of scope (no webhook server in this feature).
- *Last-writer-wins without shadow* — loses human edits or ping-pongs; no conflict detection.

---

## D6. Verify-gate & dual Spec-Review integration contracts

**Decision — Contract 1 (Verify ↔ smoke, consume as-is per FR-012)**: invoke the smoke runtime via `~/.claude/scripts/smoke_test.py` (repo `configs/claude/scripts/smoke_test.py`), `--catalog-dir smoke-catalog`, one catalog file per unit ("app").
- **Implement phase**: author/upsert one smoke test per shipped user-facing workflow via `smoke_test.py append`; the **Implement exit criterion** validates coverage by reconciling the track's shipped-workflow-id set against `smoke_test.py list --json` (a workflow id present in the track but absent from the catalog, and not marked exempt, blocks advance). Critical-path workflows MUST be tagged **tier Lite** (cumulative selection excludes higher tiers from a `--tier Lite` gate).
- **Verify phase**: `smoke_test.py run --app <unit> --tier Lite --junit <path>`; gate on **exit code** (0 pass / 1 fail-or-blocked / 2 empty-no-coverage). Exit 2 (EMPTY) is a **failure** (missing coverage ≠ pass). Per-Sub-Task traceability comes from the JUnit `<testcase>` ids.
- **Exemption**: a non-user-facing Sub-Task is marked exempt in the **track state** (with rationale, FR-011) — not in the catalog (the catalog has no such field and shouldn't).

**Decision — Contract 2 (dual `/spec-review`)**: add a **`--mode product|technical`** flag to `spec_review.sh` (sugar over the existing `SPEC_REVIEW_TEMPLATE` / `SPEC_REVIEW_STATE` env seams; defaults to current behavior). The phase parses the **verdict from `--format json`** (`[]`/`NO_ISSUES` → APPROVED; non-empty findings → NEEDS_REVIEW/BLOCKED per severity) — **not** the exit code (spec_review.sh is analysis-only and fail-open, always exits 0). For the FR-027 consensus dimension, the phase may additionally run `parallel_agent.py --validate` (FR-001 permits one-or-more commands per phase).

**Rationale**: Grounded in `smoke_orchestrator/cli.py` (append 0/2/1; run validates tier then writes JUnit, returns aggregate exit; list builds `{id,tier,steps}`) and `models.py` (cumulative `select_by_tier`; verdict EMPTY/FAIL/PASS → exit 2/1/0). `spec_review.sh` has no mode flag today (only `--spec/--plan/--tasks/--silent/--format`) but exposes `SPEC_REVIEW_TEMPLATE`/`SPEC_REVIEW_STATE` env seams, and its `main()` returns 0 regardless of findings — so the verdict must come from parsed JSON.

**Alternatives rejected**:
- *Detect missing coverage from `run` exit codes alone* — `run` only emits EMPTY (exit 2) when the **whole** tier selection is empty; a single uncovered new workflow alongside other Lite tests yields exit 0 (false pass). Per-workflow detection needs `list --json` reconciliation at Implement-exit.
- *Tag critical-path tests at Full/Full+Extra* — cumulative selection excludes them from a `--tier Lite` gate (silent miss).
- *Use `spec_review.sh` exit code as the gate* — it's fail-open (always 0); parse JSON instead.
- *Env-vars only, no `--mode` flag* — viable fallback, but FR-002 wants the identifier explicit in the invocation and auditable for drift (FR-026).

**Open risk**: repo `spec_review.sh` (parallel-agent panel) differs from the deployed `~/.claude/scripts/spec_review.sh` (older agy-only); the `--mode` flag and any change need a **bootstrap redeploy** before the lifecycle invokes the deployed path.

---

## D7. Constitution amendment & dependent-artifact sync

**Decision**: Codify the lifecycle as **both** a new Core Principle **VI. State-Gated Lifecycle** (durable non-negotiables: nine ordered phases, no skipping; hard-halt for agents / advisory-with-logged-override for humans; logged backward transitions; Verify gate IS the smoke suite; review/analyze gates reuse the existing verdict model) **and** a new top-level section **## Development Lifecycle** (the operational 9-phase→command(s) table, per-phase entry/exit/artifact, the 4-tier hierarchy + FR-028 anchoring, provider abstraction pointing to config, autodev enforcement). Version bump **MINOR → v1.1.0**, applied via `/speckit-constitution`.

**Rationale**: Mirrors the constitution's own pattern (Principle III states the rule; the "Quality Gates" section operationalizes it). The lifecycle has both a principle-altitude non-negotiable and a too-large-for-a-paragraph operational table. MINOR is the literal output of the constitution's versioning policy for "new principle or section added" (no removals/redefinitions), and matches the spec's own assumption. Reference (don't duplicate) the verdict model; push volatile provider specifics to config — preserving durability.

**Dependent artifacts to sync** (via `/speckit-constitution` + manual where the skill doesn't reach):
- **MUST update**: `.specify/templates/plan-template.md` (Constitution Check gate adds lifecycle gates); `.specify/templates/tasks-template.md` (reconcile "Tests are OPTIONAL" with mandatory per-user-facing-workflow smoke coverage — scope to lifecycle-gated, not a blanket mandate); `docs/SPEC-SYSTEMS.md` (update the old "spec→clarify→plan→tasks→implement" description to the 9-phase lifecycle); the Sync Impact Report comment atop `constitution.md`.
- **SHOULD review**: `.specify/templates/spec-template.md`; `configs/claude/config/validation_criteria.yml` (single source for the reused verdict model — verify no drift); `docs/COMMANDS.md`; `AGENTS.md` and `configs/claude/CLAUDE.md`; `.specify/extensions.yml` (phase hooks stay consistent with the phase→command map).
- **NOT modified**: `.specify/templates/constitution-template.md` (source template, per v1.0.0 precedent).

**Alternatives rejected**: section-only (buries the non-negotiable); principle-only (overloads the principle with a 9-row table); extend "Development Workflow" (dilutes SC-008's single authoritative location); MAJOR bump (no removals/redefinitions); PATCH (more than wording); hard-coding provider transition IDs (volatile).

**Open risks**: (1) MAJOR-vs-MINOR is a maintainer judgment call — flag in the amendment PR. (2) The autodev loop reads the constitution at runtime but is **not** auto-synced by `/speckit-constitution` — wiring the loop to the new gates is a separate implementation task (FR-024/SC-011). (3) `validation_criteria.yml` and `docs/COMMANDS.md` aren't touched by the skill — update manually to avoid drift.

---

## Cross-cutting consequences for the plan

- **New artifacts**: `configs/claude/scripts/lifecycle.sh` (+ `tests/bats/lifecycle.bats`); `.retired skill supply/skills/lifecycle/SKILL.md`; constitution Principle VI + Development Lifecycle section; `--mode` flag on `spec_review.sh`; config map for tier→construct + canonical-status.
- **Reused as-is**: smoke orchestrator (`smoke_test.py`), `git_ops.sh`/`git_platform.sh`/`linear_ops.sh`, `labels.yml`/`label_sync.sh`, the Atlassian MCP, `parallel_agent.py`, the 360/361 decide-core idiom.
- **Bootstrap**: changes to `spec_review.sh` and any deployed script require `./bootstrap.sh` redeploy (deployed vs repo drift is a known gotcha).
