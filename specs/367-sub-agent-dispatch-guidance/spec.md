# Feature Specification: Sub-Agent Dispatch Guidance for Skills

**Feature Branch**: `367-sub-agent-dispatch-guidance`

**Created**: 2026-06-28

**Status**: Delivered 2026-06

**Input**: User description: "make appropriate use of sub-agents for these. specifically instruct when to."

## Clarifications

### Session 2026-06-28

- Q: Which skills should gain sub-agent dispatch guidance? → A: All 89 skills (full audit).
- Q: Which kind of sub-agent should the guidance cover? → A: Both Claude-native Task sub-agents and the existing `parallel_agent.py` external CLI agents, with explicit rules for choosing between them.
- Q: Where is each skill's disposition recorded as the single source of truth? → A: Extend the existing `tool_policies` block in `command_config.yml` (add native-Task-subagent fields alongside `parallel_agents`); SKILL.md bodies carry the prose triggers that reference it.
- Q: Where do the native-vs-`parallel_agent.py` selection rules live? → A: Centralized in one referenced location (orchestration guide / references doc); each skill body carries only its own concrete trigger and links to the shared rules.
- Q: What canonical minimum-scale default gates "conditional" dispatch? → A: Dispatch only when ≥3 independent units of work exist, OR an existing per-skill scale threshold (e.g., `docs_improve_lines: 500`) is exceeded; fewer → inline.
- Q: How is audit coverage and config/prose consistency enforced? → A: An automated test (bats/pytest) wired into CI asserts every skill has a `tool_policies` disposition and that prose triggers do not contradict it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Skills tell the agent when to dispatch sub-agents (Priority: P1)

An AI assistant (Claude, Cursor, Gemini, or Codex) invokes a skill that involves multiple
independent steps (e.g., a multi-language refactor, a whole-repo audit, a docs refresh). The
skill body contains an explicit, concrete instruction telling the agent **whether** to dispatch
sub-agents, **when** the condition for dispatch is met, **how many** to dispatch, and **what each
should do**. The agent reads this guidance inline and fans the work out instead of grinding through
every step sequentially in one context.

**Why this priority**: This is the core of the request ("specifically instruct when to"). Without
concrete in-skill triggers, sub-agent use stays accidental and inconsistent. This story alone — even
applied to only the heaviest skills — delivers the primary value: faster, more parallel, less
context-starved skill execution.

**Independent Test**: Pick any orchestration-heavy skill (e.g., `refactor-python`, `docs-all`,
`repo-hygiene`), read its `SKILL.md`, and confirm it states a concrete dispatch trigger ("when N
independent targets exist, dispatch one sub-agent per target to do X"). Execute the skill against a
qualifying input and confirm the agent fans out as instructed; execute against a sub-threshold input
and confirm it stays inline.

**Acceptance Scenarios**:

1. **Given** a skill whose work decomposes into 2+ independent units, **When** an agent runs it,
   **Then** the skill provides an explicit condition under which to dispatch sub-agents and a
   description of each sub-agent's task.
2. **Given** a skill whose work is a single trivial step, **When** an agent runs it, **Then** the
   skill explicitly states that sub-agents are NOT to be used (so dispatch is never ambiguous).
3. **Given** a dispatch trigger in a skill, **When** the trigger is read, **Then** it is phrased as
   a checkable condition (count, size, independence) rather than a vague suggestion ("consider...").

---

### User Story 2 - Selection rules choose the right sub-agent mechanism (Priority: P2)

The repository exposes two sub-agent paradigms: Claude-native Task/Agent sub-agents (in-session,
read-and-fan-out, Claude-only) and the external `parallel_agent.py` cross-verification harness
(Gemini/Cursor/Codex/Antigravity, cross-platform). When a skill instructs dispatch, the agent needs
to know **which** mechanism to use. Each skill's guidance (or a shared, referenced rule set) tells
the agent which paradigm fits the task and the running platform.

**Why this priority**: Picking the wrong mechanism wastes tokens or fails outright (e.g., invoking
the Task tool on a platform that lacks it). Selection rules make the P1 guidance actionable across
all supported assistants. It depends on P1 existing but is independently testable.

**Independent Test**: For a skill that supports both mechanisms, confirm its guidance states the
selection rule (e.g., "use native Task sub-agents for parallel reads/research; use `parallel_agent.py`
for independent cross-model verification of a security-sensitive change"). Confirm the rule names the
cross-platform fallback for non-Claude assistants.

**Acceptance Scenarios**:

1. **Given** a task that is parallel information-gathering, **When** the selection rule is applied,
   **Then** it directs the agent to native Task sub-agents (or the platform equivalent).
2. **Given** a task that is independent cross-model verification, **When** the selection rule is
   applied, **Then** it directs the agent to `parallel_agent.py`.
3. **Given** a non-Claude assistant running the skill, **When** native Task sub-agents are
   unavailable, **Then** the guidance names the cross-platform path so the skill still works.
4. **Given** the existing per-skill parallel-agent policy in `command_config.yml`
   (`tool_policies`, values always/conditional/never), **When** new guidance is written, **Then** it
   is consistent with that policy and does not contradict it.

---

### User Story 3 - Every skill is audited with a recorded disposition (Priority: P3)

A contributor needs assurance that the whole skill library (88 skill directories at time of
writing; enumerated dynamically) was reviewed for sub-agent
suitability, not just the obvious heavy hitters. Each skill receives a disposition — dispatch
"always", "conditional", or "never" — and skills marked "never" carry a one-line rationale, so the
audit is auditable and future skills inherit a clear pattern to follow.

**Why this priority**: The user chose a full audit over a targeted subset. Coverage and an explicit
rationale for non-dispatch skills prevent silent gaps and give the convention durability. It builds
on P1/P2 conventions but is about completeness rather than the convention itself.

**Independent Test**: Produce the audit result and confirm every skill directory under
`.retired skill supply/skills/` appears with a disposition; spot-check that "never" skills have a rationale and
"always"/"conditional" skills carry P1-style triggers.

**Acceptance Scenarios**:

1. **Given** the full skill list, **When** the audit completes, **Then** every skill has exactly one
   recorded disposition.
2. **Given** a skill dispositioned "never", **When** its entry is read, **Then** a brief rationale
   explains why fan-out does not apply.
3. **Given** a newly added skill after this feature, **When** a contributor consults the convention,
   **Then** there is a documented pattern for how to express (or decline) sub-agent guidance.

---

### Edge Cases

- **Token-economy tension**: Dispatching sub-agents has overhead. Guidance must not trigger fan-out
  for work cheaper to do inline; triggers include a minimum-scale condition so small inputs stay
  sequential.
- **Nested dispatch / recursion**: A sub-agent must not itself fan out the same way (risk of agent
  explosion). Guidance must state that dispatched sub-agents execute their task directly and do not
  re-dispatch.
- **Platform without native sub-agents**: Cursor/Gemini/Codex may lack the Task tool; the selection
  rule must always offer a path that works on the running platform (or instruct skipping fan-out).
- **Skills that already dispatch** (e.g., `docs-all`, `plan-manage`): existing guidance must be
  reconciled, not duplicated or contradicted.
- **Sensitive-change policy interaction**: The orchestration guide already mandates parallel agents
  for security/architecture/large changes; per-skill guidance must defer to that mandate, not weaken
  it.
- **Conflicting instructions**: If a skill's body prose conflicts with its `tool_policies` entry in
  `command_config.yml`, the **config is authoritative** (disposition and `subagent_trigger` value);
  the enforcement test flags the divergence so the prose is corrected. The config is the single
  source of truth; the body is a synced restatement, never an independent store.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every skill directory under `.retired skill supply/skills/` (i.e., every directory containing a
  `SKILL.md` — 88 at time of writing) MUST be reviewed and assigned exactly one sub-agent
  disposition: "always", "conditional", or "never". Coverage MUST be enumerated dynamically, not
  asserted against a hardcoded count.
- **FR-002**: Skills dispositioned "always" or "conditional" MUST contain an explicit, in-skill
  instruction stating the concrete condition under which to dispatch sub-agents (a checkable trigger:
  count / size / independence threshold), how many to dispatch, and what each sub-agent does.
- **FR-003**: Skills dispositioned "never" MUST carry a brief rationale explaining why sub-agent
  fan-out does not apply.
- **FR-004**: Dispatch guidance MUST cover both paradigms — Claude-native Task/Agent sub-agents and
  the external `parallel_agent.py` harness — and MUST provide selection rules for choosing between
  them based on task type and running platform.
- **FR-005**: Selection rules MUST always yield a path that works on the assistant actually running
  the skill (Claude, Cursor, Gemini, Codex, Antigravity), including the cross-platform fallback when
  native sub-agents are unavailable.
- **FR-006**: The existing `tool_policies` block in `command_config.yml` MUST be the single canonical
  store for each skill's disposition; it MUST be extended with native-Task-subagent field(s)
  alongside the current `parallel_agents` field rather than introducing a parallel store. New
  guidance MUST also defer to the orchestration guide's mandatory-parallel-agent rules.
- **FR-007**: The shared native-vs-`parallel_agent.py` selection rules (including the cross-platform
  fallback) MUST live in ONE referenced, read-on-demand location —
  `configs/claude/references/sub-agent-dispatch.md`, indexed by a one-line pointer in the
  auto-loaded `configs/claude/CLAUDE.md` "Reference Index" (kept out of the auto-loaded body to
  respect the context budget enforced by `context_budget.bats`). Each skill body MUST reference
  those shared rules rather than restate them, and carry its own concrete
  dispatch trigger as human-readable prose. The trigger's **structured threshold value** is stored
  once in `command_config.yml` as `subagent_trigger` (mirroring the existing `trigger_condition`
  field for the external harness); this config value is authoritative. The SKILL.md prose MUST agree
  with it, and the enforcement test (FR-011) verifies they do not diverge. This is not a parallel
  store: config holds the canonical machine-readable value, the body holds a human-facing
  restatement kept in sync by the test.
- **FR-008**: Guidance MUST instruct that dispatched sub-agents perform their assigned task directly
  and do NOT recursively dispatch further sub-agents.
- **FR-009**: Guidance MUST respect token-economy via a canonical minimum-scale default: a skill
  dispatches only when ≥3 independent units of work exist, OR an existing per-skill scale threshold
  (e.g., `docs_improve_lines: 500`) is exceeded; below that, work is handled inline.
- **FR-010**: The phrasing of dispatch triggers MUST be directive and checkable ("when N independent
  X exist, dispatch one agent per X"), not vague encouragement ("consider using agents").
- **FR-011**: An automated test (bats/pytest, wired into CI) MUST assert that every skill has a
  `tool_policies` disposition and that each skill's prose dispatch trigger does not contradict its
  recorded disposition. The test doubles as the at-a-glance coverage record for all skills.
- **FR-012**: Existing skills that already dispatch sub-agents MUST be reconciled with the new
  convention rather than duplicated or contradicted.
- **FR-013**: A documented convention describing how future skills express (or explicitly decline)
  sub-agent guidance MUST exist in exactly ONE location — `configs/claude/references/sub-agent-dispatch.md`,
  as a subsection beneath the shared selection rules — so the pattern is durable and co-located with
  the rules it references.

### Key Entities *(include if feature involves data)*

- **Skill**: A unit in `.retired skill supply/skills/` with a `SKILL.md`. Gains a sub-agent disposition and,
  where applicable, an in-body dispatch instruction.
- **Disposition**: The classification of a skill's sub-agent suitability — one of "always",
  "conditional", "never" — aligned with the `tool_policies` vocabulary already in
  `command_config.yml`.
- **Dispatch trigger**: The checkable condition embedded in a skill that tells the agent when to fan
  out (scale, count, independence) and what each sub-agent should do.
- **Selection rule**: The decision logic mapping a task + running platform to the correct sub-agent
  mechanism (native Task sub-agents vs. `parallel_agent.py`), defined once in a shared referenced
  location and linked from skills.
- **Audit artifact**: The `tool_policies` block in `command_config.yml` (canonical dispositions) plus
  the automated coverage/consistency test that verifies every skill is represented — together they
  are the at-a-glance, enforced record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of skill directories under `.retired skill supply/skills/` have a recorded sub-agent
  disposition in the `tool_policies` block of `command_config.yml` (verified by the automated
  coverage test, which enumerates skills dynamically).
- **SC-002**: 100% of skills dispositioned "always" or "conditional" contain a checkable dispatch
  trigger (a reviewer can point to the condition, count, and per-agent task in the skill body).
- **SC-003**: 100% of skills dispositioned "never" carry a one-line rationale.
- **SC-004**: Zero contradictions between in-skill prose triggers and the `tool_policies` dispositions
  in `command_config.yml` — enforced by the automated consistency test passing in CI.
- **SC-005**: Every skill that instructs native sub-agent dispatch also states a path that works on a
  non-Claude assistant (no skill leaves a non-Claude platform without an executable option).
- **SC-006**: For a representative heavy skill, running it on a qualifying (multi-target) input
  results in observable fan-out, and running it on a sub-threshold input results in inline execution
  — i.e., the trigger demonstrably gates behavior.
- **SC-007**: A contributor can locate the "how to add sub-agent guidance to a new skill" convention
  in one documented place — `configs/claude/references/sub-agent-dispatch.md`, beneath the shared
  selection rules (pointed to from the CLAUDE.md Reference Index).

## Assumptions

- "These" refers to the full skill library (skill directories under `.retired skill supply/skills/` — 88 at
  time of writing; the clarification's "89" was an `ls` count that included `README.md`), confirmed
  via clarification; `configs/claude/skills` is the compat symlink to the same source of truth.
- "Sub-agents" covers both Claude-native Task/Agent sub-agents and the repo's existing external
  `parallel_agent.py` harness, confirmed via clarification.
- The existing `tool_policies` block in `command_config.yml` (per-skill always/conditional/never
  parallel-agent policy) is the canonical disposition store and is extended in place with
  native-Task-subagent field(s) — never replaced by or duplicated into a parallel mechanism
  (confirmed via clarification).
- The orchestration guide's existing "ALWAYS use parallel agents for security/architecture/large
  changes" rules remain authoritative; per-skill guidance defers to them.
- Guidance is authored for AI assistants as the primary readers (consistent with how `SKILL.md`
  bodies are written), with contributors as secondary readers.
- Changes are confined to skill bodies, the audit artifact, and configuration/convention docs; no
  change to `parallel_agent.py` behavior or the Task tool itself is in scope.
- Cross-platform deployment (Cursor/Gemini/Codex/Antigravity) follows the existing symlink/rules
  deployment model; no new deployment mechanism is introduced.
