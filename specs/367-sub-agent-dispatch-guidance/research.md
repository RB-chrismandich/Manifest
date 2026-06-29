# Phase 0 Research: Sub-Agent Dispatch Guidance for Skills

All four high-impact unknowns were resolved during `/speckit-clarify`. This file records those
decisions plus the grounding facts gathered while planning. No `NEEDS CLARIFICATION` remain.

## R1 — Disposition store

- **Decision**: Extend the existing `tool_policies` block in `configs/claude/config/command_config.yml`.
  Add a `subagents: always|conditional|never` field (and optional `subagent_trigger:` when
  `conditional`) to each skill entry, alongside the existing `parallel_agents` field.
- **Rationale**: `tool_policies` already encodes per-skill `parallel_agents: always|conditional|never`
  with `trigger_condition` for scale gates. Reusing it gives one canonical store, one vocabulary, and
  one place CI verifies. A second store would invite drift.
- **Alternatives considered**: (a) per-skill SKILL.md frontmatter + a separate audit doc — rejected,
  two stores to reconcile; (b) a brand-new registry doc — rejected, relocates existing data and
  duplicates the schema.

## R2 — Selection-rule location

- **Decision**: Author the native-Task-subagent vs `parallel_agent.py` selection rules (with the
  cross-platform fallback) once, as a section in `configs/claude/CLAUDE.md` (the deployed
  orchestration guide). Skills link to it and carry only their own concrete trigger.
- **Rationale**: Repeating ~15 lines of selection logic across 30+ skills bloats bodies and drifts.
  Centralizing matches the repo convention ("MCP routing defined once in the orchestration guide").
  Only `SKILL.md` *frontmatter* is auto-loaded, so per-skill bodies stay lean; the shared rules are
  read on demand.
- **Alternatives considered**: inline-in-every-skill (rejected: duplication/drift); guide-only with
  no per-skill trigger (rejected: agents would not see a concrete "when" at the point of use).

## R3 — Fan-out threshold

- **Decision**: Canonical default — dispatch only when **≥3 independent units of work** exist, OR an
  existing per-skill scale threshold is exceeded (e.g., `docs_improve_lines: 500`,
  `unique_imports >= 5`). Fewer → inline.
- **Rationale**: Sub-agent dispatch has fixed overhead; a uniform floor prevents fan-out on trivial
  inputs (token-economy). Reusing existing `trigger_condition` thresholds keeps behavior consistent
  with what `parallel_agents: conditional` skills already use.
- **Alternatives considered**: ≥2 units (rejected: too eager, overhead on small inputs); per-skill
  ad-hoc thresholds with no default (rejected: inconsistent, hard to verify uniformly).

## R4 — Enforcement

- **Decision**: Add an automated test (`tests/bats/subagent_policy.bats`, or a `tests/python/`
  pytest if assertions get complex) wired into CI. It MUST (a) enumerate skill directories
  dynamically and assert each has a `subagents` disposition in `tool_policies`; (b) assert every
  `always`/`conditional` skill body contains a trigger and every `never` skill carries a rationale;
  (c) assert no prose trigger contradicts its recorded disposition.
- **Rationale**: The repo already gates invariants with bats (`context_budget.bats`,
  `commands_doc_drift.bats`). A dynamic test makes SC-001 (coverage) and SC-004 (consistency)
  self-maintaining as skills are added.
- **Alternatives considered**: manual checklist (rejected: silently regresses); on-demand script not
  in CI (rejected: not enforced per change).

## R5 — Authoritative skill count (grounding)

- **Decision**: There are **88** skill directories under `.skillshare/skills/` (each has a
  `SKILL.md`). The spec's "89" came from an `ls` that counted `README.md`. The enforcement test
  counts directories dynamically, so no count is hardcoded.
- **Rationale**: Avoids a brittle magic number and a spec/impl mismatch.
- **Alternatives considered**: hardcode 88 in the test (rejected: breaks on the next skill added).

## R6 — Coverage gap (grounding)

- **Finding**: `tool_policies` currently has **30** entries; **58** skill directories have none.
  Implementation must add `subagents` to all 88 and backfill the 58 missing entries (with
  `parallel_agents`/`allowed`/`forbidden`/`validation_tier` as appropriate).
- **Implication**: The audit is a large, highly parallelizable classification task — a natural fit
  for sub-agent fan-out during `/speckit-implement` (one agent per batch of skills), which also
  dogfoods the very capability this feature documents.

## R7 — Native sub-agent exemplar (grounding)

- **Finding**: `docs-all` already dispatches Claude-native sub-agents via the Task tool (one per
  docs skill, continue-on-failure, merged report). It is the reference pattern for "always"-style
  native dispatch and for the trigger wording other skills should mirror.

## R8 — Cross-platform fallback

- **Decision**: The shared selection rules MUST state: native Task/Agent sub-agents are Claude-only;
  on Cursor/Gemini/Codex/Antigravity, skills either use `parallel_agent.py` (cross-platform) or run
  the work inline. No skill may leave a non-Claude assistant without an executable path.
- **Rationale**: Guidance that assumes the Task tool would silently fail on other assistants the
  repo explicitly supports.
- **Alternatives considered**: Claude-only guidance (rejected: repo is multi-assistant by design).
