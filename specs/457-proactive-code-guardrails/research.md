# Research: Proactive Code Guardrails

**Feature**: 457-proactive-code-guardrails | **Date**: 2026-07-01

All Technical Context unknowns resolved. Decisions below are grounded in direct inspection of the repository's existing assets (paths verified on branch `457-proactive-code-guardrails`).

## R1 — Registry home: extend `knowledge_base.yml`, do not create a new store

**Decision**: The anti-pattern registry lives in `configs/claude/config/knowledge_base.yml`, the existing store already managed by `learning_capture.sh` and written to by the `antipattern-detect` and `learning-loop` skills. Seeded entries use the existing entry shape (`id`, `title`, `category: antipattern`, `language`, `description`, `tags`, `confidence`, `created`, `last_seen`, `occurrences`, `source`) plus four new **optional** fields: `severity`, `detection_cue`, `prevention_rule`, `provenance`.

**Rationale**: FR-007/FR-008 require one registry and capture-to-active in one step (SC-005). The store, its writer script, its bats coverage (`learning_capture.bats`), and its doc-sync (`sync-docs`) already exist. New optional fields keep every existing entry and consumer valid (additive schema evolution).

**Alternatives considered**: (a) New `antipatterns.yml` config — rejected: creates the second registry FR-008 prohibits and severs the capture loop. (b) Encoding rules only in skill markdown — rejected: not machine-consultable by `code-quality`, and capture couldn't extend it.

## R2 — Language-specific entries reuse the existing `language` field

**Decision**: Category-level rules are one entry with `language: general`; language-specific detection cues are carried in the `detection_cue` field as a per-language map (`bash:`, `python:`, `typescript:`, `go:`, `terraform:`) within a single entry, not as per-language duplicate entries.

**Rationale**: Keeps the registry at ~32 entries instead of ~160; avoids the duplication anti-pattern this very feature warns about; `knowledge_base.yml` already enumerates these languages in its header comment.

**Alternatives considered**: One entry per language per anti-pattern — rejected: 5x entry count, drift risk between siblings.

## R3 — Severity vocabulary maps onto `validation_criteria.yml`, five classes collapse to three + two

**Decision**: Registry/audit severities are `critical`, `high`, `medium`, `low`, `info`. The first three map 1:1 onto the severity values already used in `validation_criteria.yml` (tier1 checks carry `critical`/`high`/`medium`). Verdict mapping for audit reports mirrors the existing system, where *tier membership* (not the severity label) decides blocking: any verified `critical` finding → `BLOCKED`; verified `high` in a Tier 1 domain (guardrail tags `security`, `error-handling`) → `BLOCKED`; other verified `high` → `NEEDS_REVIEW`; otherwise → `APPROVED`. `low`/`info` never affect the verdict.

**Rationale**: FR-006 mandates one severity vocabulary plugging into existing consensus flows; the constitution's Quality Gates define the verdict model this maps to.

**Alternatives considered**: Adopting the research report's five-class table verbatim with its own action column — rejected as a parallel scheme; its action semantics ("block merge", "fix before release") are expressed through the existing verdicts instead.

## R4 — Write-time guidance placement: summary in deployed guides, detail in a reference

**Decision**: A compact guardrails digest (~15–20 lines: the six categories, the iron rules — propagate error signals, validate at boundaries, secrets from env, preserve existing security controls when refining, prefer refactoring over accretion, no speculative guards) goes into `configs/claude/CLAUDE.md` (and regenerated mirrors for Gemini/Codex/Cursor/Antigravity). Full per-anti-pattern detail with detection cues and examples goes into a new on-demand reference `configs/claude/references/antipatterns.md`, indexed from the guide's Reference Index.

**Rationale**: FR-003 + SC-004 require staying inside the enforced context budget; the repo's established token-economy pattern (per `references/` + the Reference Index convention, and the context-budget history in `tests/bats/context_budget.bats`) is exactly this split.

**Alternatives considered**: Full rules in CLAUDE.md — rejected: blows the budget and violates the repo's token-economy rules. Skill-only delivery — rejected: write-time prevention must be ambient, not invocation-gated.

## R5 — Advisory enforcement: extend `code-quality`, not a new hook

**Decision**: The clarified "guidance + advisory checks" posture is implemented by extending the existing auto-triggered `code-quality` skill: add a "Registry anti-patterns" trigger/check section that consults `knowledge_base.yml` antipattern entries (including newly captured ones) and reports matches inline, explicitly non-blocking. No new PreToolUse/PostToolUse hook is added.

**Rationale**: `code-quality` already auto-triggers on security-sensitive patterns and complexity without blocking flow — the precise mechanism FR-011 describes. A new hook would duplicate its trigger surface and add latency to every edit.

**Alternatives considered**: `lint_on_edit_hook.sh` extension — rejected: that hook is linter-driven (deterministic tools), while registry matching is judgment-based and belongs in skill guidance. New blocking pre-commit — rejected by clarification Q1.

## R6 — Audit skill shape: seven sequential passes, chunking above 50 files, Critical/High cross-verification

**Decision**: New skill `ai-code-audit` (`.retired skill supply/skills/ai-code-audit/SKILL.md`). Passes run in fixed order: P0 inventory/orientation → P1 architectural integrity → P2 async & state lifecycle → P3 security → P4 logic/business-rule integrity → P5 quality/maintainability → P6 iterative regression (git-history based, skipped gracefully when history is shallow). For targets >50 source files, the skill chunks by top-level directory, runs P1–P5 per chunk, and runs P0/P6 plus report-merge globally. Critical/High findings get an independent adversarial re-check (fresh sub-agent instructed to refute using only the cited evidence) before being reported as verified; refuted findings downgrade to "unverified observations" (FR-012). Findings without a file:line evidence trace are never reported as defects (FR-005).

**Rationale**: Matches the user-supplied rubric's ordering rationale (later passes rely on earlier orientation); chunking resolves the deferred scaling question with the simplest strategy that preserves per-pass semantics; the refutation-style re-check mirrors the repo's existing `security-finding-refutation` pattern and this repo's documented false-BLOCKED lesson with full panels.

**Alternatives considered**: Full parallel-agent panel per pass — rejected by clarification Q4 (cost, known false-BLOCKED failure mode). Whole-codebase single pass regardless of size — rejected: context decay is itself a documented failure mode this feature exists to prevent.

## R7 — Seed list: 33 entries covering the 6 categories

**Decision**: Seed the registry with 33 entries (IDs continue the existing `ANTI-###` sequence). All ten structural anti-patterns documented in the source research (FR-002) are covered — the two near-identical rows "edge-case over-specification" and "phantom bugs" merge into one entry covering both:

- **Architectural/structural (10)**: refactoring avoidance / linear accretion; context-induced monolith ("return of the monolith"); cosmetic abstraction (single-impl interface adding no isolation); broken abstraction (interface bypassed by concrete references); dead/orphan module; near-duplicate function (context-loss duplication); excessive inline commenting substituting for readable logic; speculative phantom guards / edge-case over-specification (covers both research rows); vanilla style (no separation of concerns — business logic, data access, presentation mixed); shallow test coverage (tests assert presence, not behavior).
- **Async & state (5)**: un-awaited/unhandled async operation; orphan state (conditional write, unconditional read); missing teardown for listener/subscription/timer; shared-state race (non-atomic concurrent writes); empty/null/single-item collection edge cases unhandled.
- **Error handling (4)**: catch-log-return-undefined (swallowed error); catch-and-discard without propagation; generic symmetric error messages; missing boundary validation (CWE-20).
- **Security (7)**: injection via string concatenation (CWE-89/78, existing ANTI-001 updated in place); insecure temp files (CWE-377, existing ANTI-002 updated in place); hardcoded secret (CWE-798); missing resource-level authorization (IDOR); weak crypto / insecure random (CWE-327); permissive CORS / missing security headers; sensitive data in logs.
- **Dependency/supply-chain (3)**: hallucinated/unverified package; stale or vulnerable version pin; environment-sensitive code without dependency pinning or config validation ("worked on my machine").
- **Iteration/process (4)**: security-control removal during refinement; convention drift across sessions (naming/pattern abandonment at integration boundaries); literal prompt fixation (rigid interpretation, no architectural extrapolation); bug déjà vu (same error class recurring across sessions — prevention rule: consult and capture to this registry).

**Rationale**: Satisfies SC-001 (6/6 categories, ≥25 entries) and FR-002's "at minimum the ten documented structural anti-patterns" while every entry stays distinct and actionable; existing ANTI-001/002 (shell injection, insecure tempfiles) already cover part of the security column and are updated in place rather than duplicated.

## R8 — Derived-artifact regeneration chain

**Decision**: Any skill add/change triggers the full regeneration chain before PR: `generate_cursor_rules.sh` (cursor `.mdc`), `generate_commands_doc.py` (`docs/COMMANDS.md` count/table), Gemini/Codex/Antigravity guide mirrors, `command_config.yml` `tool_policies` entry for `ai-code-audit` (policy: `conditional` — parallel verification only for Critical/High re-checks), then the real pre-commit run (`--from-ref origin/main`) and `bats tests/bats/` (context budget, drift tests).

**Rationale**: Documented repo failure modes: cursor-rules/eof-fixer conflicts, COMMANDS.md count drift, context-budget breakage, and changed-file CI gates dragging in unregenerated files.

## R9 — Verify-gate (smoke) strategy

**Decision**: The seeded-fixture acceptance test doubles as the critical-path smoke for the audit workflow: `tests/fixtures/audit-seeded/` contains a ≤15-file toy project planting one instance each of: swallowed async error, hardcoded credential, dead module, single-impl interface, missing teardown, unvalidated boundary input. A bats test (`knowledge_base_registry.bats`) validates registry schema/coverage statically; the fixture audit run validates SC-002 behaviorally during implementation review (agent-executed, documented in quickstart.md).

**Rationale**: Constitution VI requires shipped user-facing workflows to have passing critical-path smoke coverage; a skill's behavior can't be bats-asserted directly, so the deterministic parts (schema, budget, capture round-trip) get bats tests and the behavioral part gets a scripted fixture procedure with pass criteria.
