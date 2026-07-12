# Feature Specification: emdash Support (Full Config Inheritance)

**Feature Branch**: `483-emdash-support`

**Created**: 2026-07-12

**Status**: Draft

**Input**: User description: "Add support for emdash and ensure it inherits all skills / agents / hooks /etc."

## Overview *(context — non-normative)*

**emdash** (`generalaction/emdash`, YC W26) is an open-source desktop application — an "Agentic Development Environment" — that runs multiple coding agents **in parallel, each in its own Git worktree**. It does not replace an agent; it **launches the user's existing agent CLIs** (Claude Code, Codex, Gemini, Cursor, and ~30 others) as child processes inside a worktree checkout, using the user's real home directory.

This matters for scope: unlike the platforms Manifest already supports (Claude, Cursor, Gemini, Codex, Antigravity), emdash **has no file-based configuration directory** that Manifest could deploy into (its state is an internal database). Because an emdash-launched agent runs with the real home directory and inside a normal repository checkout, it **already inherits the full Manifest configuration transitively** — the skills, subagents, hooks, MCP servers, orchestration guide, and settings Manifest deploys to the home directory, plus the repository's committed guidance files. "Adding emdash support" is therefore a **recognition, verification, and gap-closing** feature, **not** a new deployment target.

The decided scope for this feature is **first-class recognition without a deploy tree**: guarantee and verify that inheritance, make emdash worktrees immediately usable for this repository, ensure Manifest's hooks/settings coexist with the hook wiring emdash injects, and make Manifest's docs and diagnostics recognize emdash. Populating emdash's own in-app catalogs is out of scope (see Non-Goals).

## Clarifications

### Session 2026-07-12

- Q: How should inheritance parity be verified, given emdash is a GUI app with no CLI? → A: **Hybrid** — an automated test that reproduces emdash's launch environment (real `HOME`, worktree working directory, injected `EMDASH_HOOK_*` environment, and the settings emdash writes on spawn) and asserts full config resolution, **plus** a documented one-time manual smoke run against the actual emdash application.
- Q: emdash writes its own hook wiring into the repo's tracked `.claude/settings.local.json` per spawn and gitignores it — how should the collision be handled? → A: **Verify preservation + document** — rely on emdash's idempotent merge, verify Manifest's committed hooks survive a spawn, and document the ignore-rule/tracked-file interaction and how to keep the working tree clean. No active guard/restore mechanism and no untracking/restructuring of the file.
- Q: Which agents must have verified inheritance parity for the feature to be "done"? → A: **Claude Code is formally verified** (primary); Codex, Gemini, and Cursor are documented as inheriting via the same transitive `HOME`+worktree mechanism on a best-effort basis (not formally tested).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Manifest configuration is fully active in emdash sessions (Priority: P1)

A Manifest user opens their repository in emdash and starts a coding-agent task. That task runs in an emdash-managed worktree. The user expects the agent to behave **exactly as it would in a terminal session inside the repository**: every Manifest skill is invocable, every Manifest subagent is dispatchable, every Manifest hook fires, every configured MCP server is available, and the orchestration guide plus the repository's committed guidance are in effect.

**Why this priority**: This is the literal request ("ensure it inherits all skills / agents / hooks"). Without it, agents run through emdash are second-class and the feature delivers nothing. It is the Minimum Viable Product.

**Independent Test**: Open this repository in emdash, launch the primary supported agent in a worktree, and verify against a fixed inheritance checklist that (a) a known Manifest skill triggers, (b) a Manifest subagent can be dispatched, (c) a Manifest hook fires, (d) a configured MCP tool is available, and (e) the orchestration guide and repo guidance are loaded — matching the results of the same checklist run in a terminal session.

**Acceptance Scenarios**:

1. **Given** the Manifest home deployment has been run and the repository is opened in emdash, **When** the user starts an agent task in an emdash worktree, **Then** the agent can invoke the same Manifest skills that are available in a terminal session in that repository.
2. **Given** an active emdash agent session, **When** the user or agent triggers an action that a Manifest hook is configured to intercept, **Then** the hook fires with the same effect as in a terminal session.
3. **Given** an active emdash agent session, **When** the agent needs a Manifest-provided subagent or MCP server, **Then** the subagent is dispatchable and the MCP server is reachable.
4. **Given** an active emdash agent session, **When** the agent reasons about the task, **Then** the Manifest orchestration guide and the repository's committed guidance (project instructions, agent instructions) are in effect.

---

### User Story 2 - emdash worktrees are immediately functional (Priority: P2)

When emdash creates a fresh worktree for this repository, the agent session inside it has everything it needs to actually do work: the untracked/local files the repository depends on are present, and any required environment setup has run — so the project's verification and tooling work without the user hand-fixing the worktree.

**Why this priority**: emdash worktrees are separate working directories that do **not** receive a repository's untracked/ignored files by default, and start without a prepared environment. Without this, agents land in broken environments (missing local config, no virtualenv/dependencies) even though config inheritance (US1) succeeds. It enables real work, but inheritance is still demonstrable without it, so it ranks below US1.

**Independent Test**: Have emdash create a fresh worktree of this repository, then confirm (a) the declared untracked/local files are present in the worktree and (b) the project's standard verification entry point runs successfully without manual setup.

**Acceptance Scenarios**:

1. **Given** the repository declares which untracked/ignored files a worktree needs, **When** emdash creates a new worktree, **Then** those files are present in the worktree.
2. **Given** the repository declares required environment setup, **When** emdash creates a new worktree, **Then** the setup runs so that the project's verification/tooling succeeds without manual intervention.
3. **Given** a secret-bearing local file is needed in the worktree, **When** it is made available to the worktree, **Then** it is not added to version control by the mechanism that provisions it.

---

### User Story 3 - Manifest recognizes, documents, and diagnoses emdash (Priority: P3)

A user can discover from Manifest's documentation that emdash is a supported way to run Manifest-configured agents, understand the prerequisites and setup, and rely on Manifest's diagnostics to confirm the inheritance path is intact and to flag the one known coexistence caveat (emdash injecting its own hook wiring into settings files).

**Why this priority**: Improves discoverability, onboarding, and safety, and prevents silent breakage from the hooks/settings coexistence surface — but inheritance (US1) and functional worktrees (US2) work without it. It is valuable polish and a safety net, not a prerequisite.

**Independent Test**: Run Manifest's environment diagnostic and confirm it reports whether emdash is present and whether the inheritance path is intact, including the hook-coexistence caveat; and confirm the documentation lists emdash with accurate prerequisites and setup steps.

**Acceptance Scenarios**:

1. **Given** emdash is installed on the machine, **When** the user runs Manifest's environment diagnostic, **Then** it reports emdash detection and the status of the inheritance path.
2. **Given** the coexistence caveat exists (emdash writing hook wiring into settings files), **When** the diagnostic runs, **Then** it surfaces the caveat and whether Manifest's committed settings/hooks are intact.
3. **Given** a new user wants to use Manifest with emdash, **When** they follow Manifest's documentation, **Then** they can reach a working Manifest-configured agent session in an emdash worktree without reading source code or contacting a maintainer.

---

### Edge Cases

- **Home deployment not run**: If Manifest's home deployment has not been performed, an emdash session inherits only the repository's committed config, not home-deployed skills/subagents/hooks/MCP. The documentation must state that running the Manifest home deployment is a prerequisite, and the diagnostic should detect this state.
- **Unsupported agent selected in emdash**: emdash can launch agents Manifest does not configure. In that case inheritance is limited to whatever that agent natively reads; this must be documented as out of the guaranteed-parity set (best-effort only).
- **Hook wiring collides with a tracked settings file**: emdash writes its hook configuration into a settings file that Manifest may track in version control, and may add that path to ignore rules. This must not drop or corrupt Manifest's committed hooks/permissions, must not produce surprising version-control state, and any residual behavior must be documented.
- **Untracked secrets absent from a worktree**: A worktree that needs a local secret file (e.g. environment/config) will lack it unless explicitly provisioned; the provisioning mechanism must not commit secrets.
- **Parallel worktrees writing shared home settings**: When emdash injects home-scoped hook wiring, multiple concurrent worktree sessions may write the same shared home settings file; the outcome (last-writer, races) must not corrupt Manifest's home settings.
- **Agent config resolution under emdash's launch/protocol mode**: The agent may be driven through a structured protocol rather than an interactive terminal; the feature must verify that standard config resolution (skills/subagents/hooks/MCP) still applies in that mode, and document any capability that does not.
- **Worktree located outside the main checkout**: emdash worktrees live outside the primary repository path; any Manifest behavior that assumes an absolute path under the main checkout, or relies on the current working directory being the main repository, must still function (or be documented as a limitation).
- **emdash version drift**: emdash's launch environment and hook-injection behavior may change between releases; support targets the behavior of the current release and states the version basis.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A coding agent launched by emdash inside a worktree of a Manifest-configured repository MUST be able to invoke the same Manifest **skills** available to that agent in a terminal session (both home-deployed and repository-committed skills).
- **FR-002**: Manifest-provided **subagents** MUST be dispatchable in emdash-launched agent sessions, equivalently to a terminal session.
- **FR-003**: Manifest-configured **hooks** MUST fire in emdash-launched sessions, and emdash's own injected hook wiring MUST coexist with them without disabling or overriding Manifest's hooks.
- **FR-004**: **MCP servers** configured by Manifest MUST be available to emdash-launched agents, equivalently to a terminal session.
- **FR-005**: The Manifest **orchestration guide** and the repository's committed guidance (project and agent instruction files) MUST be in effect in emdash-launched sessions.
- **FR-006**: The repository MUST provide a **committed emdash project configuration** that (a) declares the untracked/ignored files an emdash worktree needs so they are preserved into each worktree, and (b) declares any environment setup required for a fresh worktree to be functional.
- **FR-007**: The feature MUST verify that Manifest's committed hooks/permissions survive emdash writing its hook configuration into the tracked `.claude/settings.local.json` on spawn — relying on emdash's idempotent merge rather than an active guard/restore mechanism — and MUST document the ignore-rule/tracked-file interaction and how to keep the working tree clean. It MUST NOT add a runtime guard/restore mechanism and MUST NOT untrack or restructure that file to avoid the collision.
- **FR-008**: Manifest MUST NOT create a home configuration directory or deployment tree for emdash (no home `emdash` config directory, no `configs/emdash/` tree); emdash support MUST rely on the transitive inheritance path, since emdash reads no such tree.
- **FR-009**: Manifest **documentation** MUST describe emdash as a supported harness for running Manifest-configured agents, including prerequisites (home deployment completed; a supported agent installed and selected) and setup steps.
- **FR-010**: Manifest's **environment diagnostics** MUST detect emdash and report whether the inheritance path is intact, surfacing the hooks/settings coexistence caveat.
- **FR-011**: Inheritance parity MUST be verified by a **hybrid method**: (a) an **automated test** that reproduces emdash's launch environment — real `HOME`, worktree working directory, injected `EMDASH_HOOK_*` environment, and the settings emdash writes on spawn — and asserts the agent resolves the full Manifest configuration surface (skills, subagents, hooks, MCP, guides); and (b) a **documented one-time manual smoke procedure** run against the actual emdash application. **Claude Code MUST be the formally verified agent.**
- **FR-012**: The feature MUST document the **prerequisite and boundary conditions** for guaranteed inheritance: home deployment done, a Manifest-supported agent selected, and current emdash release behavior. Specifically, **Codex, Gemini, and Cursor MUST be documented as inheriting via the same transitive `HOME`+worktree mechanism on a best-effort basis** (not formally verified); agents emdash can launch that Manifest does not configure are out of the guaranteed-parity set.

### Key Entities *(include if feature involves data)*

- **emdash harness**: The external desktop application that launches agent CLIs in parallel Git worktrees using the real home directory. Has no Manifest-shaped file-config directory; keeps its own state and its own separate in-app catalogs.
- **emdash worktree**: A standard Git worktree emdash creates for a task (under the user's emdash worktrees directory). Contains the repository's committed files by default; does not contain untracked/ignored files unless provisioned.
- **emdash project configuration**: A committed, repository-root configuration file recognized by emdash that declares which untracked files to preserve into worktrees and what setup to run — the single per-repository surface this feature adds.
- **Manifest configuration surface**: The skills, subagents, hooks, MCP servers, orchestration guide, and settings Manifest deploys to the home directory (and mirrors), plus the repository's committed guidance — the set that must be inherited.
- **emdash injected hook configuration**: The hook wiring emdash writes into agent settings files on each session spawn (to connect the agent to emdash's callback service) — the primary coexistence surface with Manifest's settings/hooks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Against the automated launch-environment simulation, **100%** of the Manifest skills, subagents, hooks, and MCP servers active in a terminal **Claude Code** session in the repository are also resolvable in the simulated emdash session; and the one-time manual smoke run confirms the same against the actual emdash application.
- **SC-002**: A **freshly created** emdash worktree of this repository passes the project's standard verification entry point with **no manual environment fixup**.
- **SC-003**: A Manifest hook that fires in a terminal Claude Code session **also fires** in the emdash (or simulated) session, and Manifest's committed hooks remain **present in the merged settings** after emdash has written its hook configuration on spawn.
- **SC-004**: A user following the emdash setup documentation reaches a working, fully-inherited Manifest agent session in an emdash worktree **without reading source code and without maintainer assistance**.
- **SC-005**: Running Manifest's environment diagnostic **reports emdash presence and inheritance status** (including the hook-coexistence caveat) in its output.
- **SC-006**: **No** home configuration directory and **no** `configs/emdash/` deployment tree are created for emdash (verifiable: the home deployment produces no emdash config directory and the repository contains no emdash deploy tree).

## Non-Goals

- Deploying a `configs/emdash/` tree or a home `emdash` configuration directory (emdash reads no such tree; it would be inert).
- Registering emdash as a parallel-agent provider (emdash is an external harness that *runs* agents, not an agent invoked by Manifest's parallel-agent orchestration).
- Populating emdash's **own** in-app catalogs so Manifest content appears in emdash's panels — i.e. mirroring skills into emdash's separate skills store, registering MCP servers into emdash's MCP catalog, or seeding its prompt library. (Agents still *use* Manifest's skills/MCP transitively; only emdash's UI listing is unaddressed. Candidate future extension.)
- Installing emdash itself, or managing emdash application settings that live in its internal database.
- Guaranteeing parity for agents emdash can launch that Manifest does not configure.

## Assumptions

- The user installs emdash themselves (desktop app); Manifest does not install or update it.
- Manifest's home deployment has already run, so the home configuration (skills, subagents, hooks, MCP, orchestration guide, settings) is populated before emdash launches an agent.
- emdash launches agent CLIs with the real home directory and with the working directory set to a standard Git worktree of the repository — the mechanism by which inheritance occurs. (Observed in the current emdash release: standard worktrees and a real-home launch environment.)
- The primary agent for verification is **Claude Code**, the platform Manifest most fully configures; other Manifest-configured agents (Codex, Gemini, Cursor) inherit through the same transitive mechanism where installed and selected.
- The agent's normal configuration resolution (home + repository) is honored when launched by emdash; confirming this under emdash's launch/protocol mode is the core verification task, not an assumption to take on faith.
- The repository's tracked settings file used by the agent is a genuine coexistence surface with emdash's injected hook wiring; the feature verifies and preserves its integrity rather than assuming no conflict.
- "All skills / agents / hooks / etc." refers to the existing Manifest configuration surface reaching emdash sessions — not an expansion of what Manifest configures.
