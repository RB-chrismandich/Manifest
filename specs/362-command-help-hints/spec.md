# Feature Specification: Command Discovery & Workflow Guidance

**Feature Branch**: `362-command-help-hints`

**Created**: 2026-06-21

**Status**: Delivered 2026-06

**Input**: User description: "Improve experience / help for available commands and workflow hints / reminders"

## Clarifications

### Session 2026-06-21

- Q: Cross-platform scope for v1 — Claude Code only, or full parity across all five agents? → A: Full parity across all five supported agents (Claude Code, Cursor, Gemini, Codex, Antigravity) ships in v1.
- Q: Feature scope boundary — read-only guidance, or also command management? → A: Read-only guidance only (discover/search/hint/remind); creating, editing, enabling, or disabling commands is out of scope (owned by retired skill supply / sync-skills / services.yml).
- Q: Command category taxonomy — fixed curated set, freeform, or derived? → A: Fixed curated taxonomy; each command maps to exactly one category, unmapped commands fall to "uncategorized". (Grouping is decoupled from skill names — no mass rename required.)
- Q: Hints/reminders default state & opt-out granularity? → A: On by default; opt-out is both global (single kill-switch) and per-category (hints vs reminders vs discovery), plus a verbosity level.
- Q: Discovery entry-point form — interactive command, generated doc, or both? → A: Both — an interactive in-session discovery command plus a generated reference doc (`docs/COMMANDS.md`), both derived from the same source.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find the right command fast (Priority: P1)

A developer working in the repository wants to accomplish a task but cannot recall which of the 70+ available commands fits. They invoke a single discovery/help entry point and receive a current, categorized, searchable list of commands — each with a one-line description and a "when to use" cue — without having to open individual skill files or trust a hand-maintained document that may be stale.

**Why this priority**: Discoverability is the core of the request ("help for available commands"). With dozens of commands, the inability to find the right one is the single biggest friction point, and it blocks people from using the rest of the system effectively. This story alone delivers a usable MVP.

**Independent Test**: With nothing else built, a user runs the discovery entry point, searches for a task intent (e.g., "clean up branches"), and locates the correct command. The returned list is verified to match the actually-installed command set (no missing or phantom entries).

**Acceptance Scenarios**:

1. **Given** the repository has N installed commands, **When** the user requests the command list, **Then** all N commands appear with a one-line description and category, and no uninstalled command is listed.
2. **Given** the user knows only the task ("review open PRs") not the command name, **When** they search by intent or keyword, **Then** the matching command(s) are surfaced ranked by relevance.
3. **Given** a command exists, **When** the user views its entry, **Then** they see when to use it (purpose/trigger) clearly enough to choose it over similar commands.

---

### User Story 2 - Contextual workflow hints at the right moment (Priority: P2)

At recognized points in a workflow — about to commit, opening a pull request, starting a language-specific refactor, or hitting high context usage — the system surfaces a short, relevant hint that names the appropriate command(s), so the user learns the intended workflow without memorizing it. Unrelated actions produce no hint.

**Why this priority**: Surfacing the right command at the right moment turns a passive catalog (P1) into active guidance, which is the "workflow hints" half of the request. It depends on P1's notion of "which command fits a situation" but adds clear standalone value.

**Independent Test**: Trigger a recognized moment (e.g., a commit) and confirm a relevant hint naming the appropriate command appears; perform an unrelated action and confirm no hint appears.

**Acceptance Scenarios**:

1. **Given** the user is about to perform a recognized workflow action, **When** that moment occurs, **Then** a concise hint naming the relevant command is surfaced.
2. **Given** the user performs an action with no associated guidance, **When** that action occurs, **Then** no hint is surfaced (no false positives).
3. **Given** more than one hint could apply to a single moment, **When** the moment occurs, **Then** hints are de-duplicated and prioritized so the user sees the most relevant guidance, not a pile.

---

### User Story 3 - Tunable reminders that never become noise (Priority: P3)

The system issues best-practice reminders (e.g., token-economy discipline, running verification before committing, stale-plan nudges). Reminders are relevance-gated and rate-limited, and the user can disable them — globally or per-category — or adjust verbosity, with every such setting reliably respected.

**Why this priority**: Reminders are the lowest-risk, highest-annoyance part of the request. They add polish, but without strict noise control and an opt-out they actively harm the experience — so they ship last, after discovery and hints prove their value.

**Independent Test**: Confirm a reminder fires at most once per configured context/interval, disable reminders via the documented setting, and confirm zero reminders fire afterward.

**Acceptance Scenarios**:

1. **Given** a best-practice reminder is eligible, **When** its triggering context recurs within the rate-limit window, **Then** it is not repeated.
2. **Given** the user disables hints/reminders, **When** any triggering context occurs, **Then** no hint or reminder is surfaced.
3. **Given** the user sets a verbosity level, **When** contexts occur, **Then** only reminders at or above that level are surfaced.

---

### Edge Cases

- A command is **added, renamed, or removed**: the catalog and any published reference reflect the change without manual editing, and drift between a published reference and the source is detectable.
- A command is **unavailable in the current context** (unsupported agent platform, or a disabled service toggle): the help marks it unavailable rather than recommending it.
- **Hint/reminder overload**: relevance gating and rate-limiting prevent floods; the user opt-out fully suppresses them.
- **Conflicting or duplicate guidance** for a single moment: guidance is de-duplicated and prioritized.
- **Context-budget pressure**: discovery/help and hint content must not materially bloat the agent's per-turn context; oversized content is summarized or paginated rather than dumped.
- **No reasonable match** for a search: the system says so plainly instead of returning an irrelevant command.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide two discovery surfaces sharing one source — an interactive in-session command and a generated reference doc (`docs/COMMANDS.md`) — each listing every available command with a concise one-line description and a category, sourced from the authoritative command metadata.
- **FR-002**: Users MUST be able to find a command by task intent or keyword (search/filter), not only by exact name. ("Intent" here means a deterministic keyword/token/substring match over name, category, description, and when-to-use — not semantic/NLP search.)
- **FR-003**: For each command, the help MUST convey when to use it (purpose/trigger) so users can distinguish it from similar commands.
- **FR-004**: The command reference MUST stay synchronized with the source of truth — newly added, renamed, or removed commands appear or disappear without manual edits, and drift between any published reference and the source MUST be detectable.
- **FR-005**: System MUST surface a relevant workflow hint at recognized workflow moments, naming the appropriate command(s), and MUST NOT surface hints for unrelated actions.
- **FR-006**: Hints and reminders MUST be relevance-gated and rate-limited to avoid noise, including de-duplication when multiple could apply to one moment.
- **FR-007**: Hints and reminders MUST be enabled by default. Users MUST be able to opt out both globally (a single kill-switch) and per-category (independently silencing hints, reminders, or discovery), and to set a verbosity level. Every such setting MUST be reliably respected.
- **FR-008**: The help/discovery experience MUST indicate commands that are unavailable in the current context — where "unavailable" means the command's service is disabled in `services.yml`, or the command is not deployed to the active agent platform (per the existing per-platform deployment config) — rather than recommending them.
- **FR-009**: Hints MUST be delivered as one-shot output at the triggering moment, not persisted into the always-loaded per-turn context. Any always-loaded help/reminder content MUST stay within the project's established context budget (enforced by the existing `context_budget` check) and MUST NOT materially increase per-turn context cost beyond it.
- **FR-010**: The discovery list MUST present commands grouped by category, drawn from a fixed curated taxonomy (e.g., git/PR, docs, security, planning, skills, infra, meta), to aid scanning. Each command belongs to exactly one category; unmapped commands appear under "uncategorized".
- **FR-011**: The experience MUST be available at parity across all five supported agent platforms in v1 — Claude Code, Cursor, Gemini, Codex, and Antigravity — using each platform's existing adapter convention (e.g., Claude skills, Cursor `.mdc` rules, `GEMINI.md`/`AGENTS.md` guides). A platform-specific capability gap (if any surfaces during planning) MUST be explicitly documented, not silently dropped.

### Key Entities *(include if feature involves data)*

- **Command Entry**: one available command — name, one-line description, category, when-to-use/trigger, and current availability status. Derived from the authoritative skill metadata; never hand-duplicated as a second source.
- **Workflow Moment**: a recognized point in a user's workflow (e.g., pre-commit, PR open, refactor start, high context usage) capable of triggering a hint.
- **Hint / Reminder**: a short contextual message tied to a workflow moment or best practice, carrying relevance and rate-limit metadata plus an enabled/verbosity state.
- **Guidance Preference**: user-controlled settings governing guidance — a global enable/disable, independent per-category toggles (hints / reminders / discovery), and a verbosity level. Default state: all enabled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can locate the correct command for a stated task within the first screen of results (or under 30 seconds) without opening individual command files.
- **SC-002**: Immediately after a command is added or removed, the published command reference matches the installed command set with zero drift.
- **SC-003**: Measured against the registered set of Workflow Moments (the canonical list in User Story 2 — pre-commit, PR open, refactor start, high context usage) plus a fixed sample of unrelated actions: the relevant command is surfaced for at least 90% of registered moments, and no more than 5% of the unrelated-action sample produces a hint.
- **SC-004**: Reminders fire at most once per configured context/interval, and a single opt-out action results in zero subsequent reminders.
- **SC-005**: In a fresh session with no prior command knowledge, a reviewer (or agent) tracing the surfaced guidance can complete a target multi-step workflow (verify → commit → open PR) end-to-end using only the hints/discovery output — each step's next command is reachable from the previous step's guidance. Evaluated by tracing the hint chain, not by a population-level percentage.
- **SC-006**: The discovery/help and hint content stays within the project's per-turn context budget, verifiable by the existing context-budget check passing.

## Assumptions

- **Audience**: Both human developers (primary beneficiaries of discovery/help) and the AI agents (primary beneficiaries of behavior-shaping hints/reminders) are in scope; the human discovery experience leads.
- **Source of truth**: Each command's `SKILL.md` frontmatter in `.retired skill supply/skills/` is the authoritative metadata. Today that frontmatter carries only `name` and `description`; this feature needs two more facets — **when-to-use** and **category** (FR-001/003/010). *when-to-use* is **derived** from the existing "Use when …" convention already present in most skill descriptions (no new field). *category* is an **optional, additive, backward-compatible** frontmatter field whose value MUST come from a **fixed, curated taxonomy** (a small defined set, e.g., git/PR, docs, security, planning, skills, infra, meta); each command maps to exactly one, and commands without it fall to an "uncategorized" group. A taxonomy config file defines the *valid* category values and may hold an explicit, auditable `overrides` map for skills not yet carrying the field; per-skill frontmatter remains authoritative for assignment where present (so the config is not a competing assignment source). Grouping is therefore decoupled from skill names — no skill renaming is required to achieve categorized discovery. Any human-readable reference (e.g., `docs/COMMANDS.md`) is generated from or validated against this source — never a competing source.
- **Delivery shape**: Two on-demand discovery surfaces (an interactive in-session command and a generated `docs/COMMANDS.md`, both from one source) plus proactive, **event-driven, one-shot** hints. Hints are surfaced at the triggering moment as transient output and are NOT injected into the always-loaded per-turn system prompt, so they accrue no per-turn context cost. Any standing always-loaded content (e.g., a single reminder line, as the existing `UserPromptSubmit` hook does) is bounded by the project's context budget.
- **Cross-platform**: Full parity across all five supported agents (Claude Code, Cursor, Gemini, Codex, Antigravity) is **in scope for v1** (per Clarifications 2026-06-21), each via its existing adapter convention and deployment/symlink patterns.
- **Token economy is a hard constraint**: the existing context-budget check governs acceptable context cost for any always-loaded content.
- **Availability**: Two existing sources determine availability — `services.yml` toggles (service enabled/disabled) and the existing per-platform deployment mapping (which agent platforms a command is deployed to). No new availability metadata field is introduced.
- **No new external services**: the feature builds on existing configuration, hook, and deployment infrastructure; it introduces no new runtime dependency.
- **Out of scope (v1)**: command *management* — creating, editing, enabling, or disabling commands — is explicitly excluded (per Clarifications 2026-06-21). Those actions remain owned by `retired skill supply`, `sync-skills`, and `services.yml`. This feature only *surfaces* and *guides toward* existing commands (read-only).
