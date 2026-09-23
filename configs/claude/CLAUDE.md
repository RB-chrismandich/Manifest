# Claude Orchestration Guide

This document defines current-host native sub-agent dispatch, planning, and validation.

## Risk-based review routing

Use a single capable reviewer by default. Independent review is risk-based:
escalate only for a trust-boundary change, destructive behavior, broad
compatibility or deployment impact, conflicting evidence or unresolved
uncertainty, or genuinely independent codebase-wide tracks. Counts of files,
packages, modules, languages, keywords, and units do not independently escalate.

## Token Economy (always on)

Apply at all times, in every session:

- Lead with the result. No filler ("Sure", "Here's the…"), no closing summaries.
- Match response length to the task; don't re-explain code you just wrote unless asked.
- Use programmatic edit tools for targeted edits; never reprint a whole file for a small change.
- If an implementation detail is genuinely ambiguous, ask ONE targeted question instead of guessing.
- Read what a change depends on (types, signatures, callers); skip speculative
  whole-tree crawls and re-reads of unchanged files. Don't starve context —
  a wrong edit costs more than one extra dependency read.
- Default dispatched agents to Sonnet through the current host's native control;
  OMP uses `task.agentModelOverrides`, never a task-item `model` field.

`/token-conserve` re-asserts this mode if drift is noticed mid-session.

## Native Sub-Agent Dispatch

Use the current host's supported native mechanism: OMP uses `task` and `hub`;
Claude Code uses its discovered native Agent/background collection. Preserve
OMP specialist selection and use only actually discovered Claude agent types.
The parent validates evidence and aggregates results. The authoritative
[shared dispatch contract](references/sub-agent-dispatch.md) defines child
limits, the narrow delegate-runner exception, and `DEGRADED` behavior.

## Reference Index

Read on demand (NOT auto-loaded). You MUST read the reference before related tasks:

- `~/.claude/references/orchestration.md` — Read when coordinating OMP task batches or validating independent review.
- `~/.claude/references/git-platform.md` — Read when automating PRs, branch detection, or native forge CLI failures.
- `~/.claude/references/layout.md` — Read when modifying config trees or mapping file locations.
- `~/.claude/references/sub-agent-dispatch.md` — Read before a skill dispatches sub-agents: native Task vs
  OMP task batches, selection rules, and inline `DEGRADED` behavior.
- `~/.claude/references/spec-artifact-discovery.md` — Read before a spec-* skill reads
  planning artifacts: speckit vs superpowers layout detection + precedence.
- `~/.claude/references/code-constitution.md` — Read BEFORE creating or modifying
  source: 13 articles, ceilings, per-language annexes (`constitution/<lang>.md`).
- `~/.claude/references/antipatterns.md` — Read before writing or refactoring code:
  guardrail registry (detection cues + prevention rules).
- `~/.claude/references/doc-concision.md` — Read before writing or auditing docs:
  per-type line caps, fan-out-to-sub-pages rule, fluff blocklist (`docs_lint.py`).
- `~/.claude/references/harness-routing.md` — Read before cross-harness
  skill/agent work: OMP dispatch semantics and single-provider policy boundaries.

## Proactive Coding Guardrails (always on)

While writing: propagate error signals (never log-and-drop); validate inputs at
boundaries; secrets from env only; await/route every async op; pair
setup/teardown; serialize shared writes; refactor before accreting; no
speculative guards, single-use abstractions, or dead code; verify new deps
exist. When refining, NEVER silently remove security controls or validation.
Registry: `~/.claude/config/knowledge_base.yml`; `/ai-code-audit` = full audit.

## Proactive Decision Framework

Use risk-based review routing. One capable reviewer is the default. Escalate
only for a trust-boundary change, destructive behavior, broad compatibility or
deployment impact, conflicting evidence or unresolved uncertainty, or genuinely
independent codebase-wide tracks. File, package, module, language, keyword, and
independent-unit counts are not escalation conditions.

## Validation Criteria

- **Tier 1 (blocking)**: security, error handling, and breaking changes.
  **Tier 2 (advisory)**: bugs, performance, maintainability, tests.
- Authoritative weights: `~/.claude/config/validation_criteria.yml`.

## Skills

Skills live in `~/.claude/skills/` (deployed from the repo's
`.apm/skills/`). Each skill's `SKILL.md` frontmatter (`name`,
`description`) is the **authoritative registry** — Claude Code auto-loads every
description at session start, so no table is duplicated here. Per-skill
OMP dispatch policy (always/conditional/never) lives in
`~/.claude/config/command_config.yml` under `tool_policies`.

Common entry points: `/git-commit`, `/project-verify`, `/<lang>-refactor`,
`/docs-all`, `/plan-manage`, `/env-check`, `/session-checkpoint`,
`/version-pin`. `/help` searches the full catalog by task.

**Skills are plugin bundles**: `/<bundle>:<name>`; refresh with
`claude plugin update <bundle>@manifest`. Others read `~/.manifest/skills`.

### Security Review Skill

`code-audit` activates for an explicit security review or changed behavior at a
security boundary; vocabulary and complexity metrics alone do not activate it.

## Plan Management

Plans are `~/.claude/.plans/YYYYMMDD-short-description.md` (copy `TEMPLATE.md`);
lifecycle CREATE → ACTIVE → `.archive/` or `.abandoned/`. Review existing plans
before creating one; 7+ days untouched means update, complete, or abandon.
`/plan-manage` runs the whole lifecycle. Details: `~/.claude/.plans/README.md`.
