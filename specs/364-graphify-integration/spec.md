# Feature Specification: Graphify Integration

**Feature Branch**: `364-graphify-integration`

**Created**: 2026-06-28

**Status**: Draft

**Input**: User description: "integrate 'graphify' into our project to ensure it's integrated into the system the project provides.. https://github.com/safishamsi/graphify"

## Overview

Graphify is an AI-powered knowledge-graph generator that turns a codebase (plus docs, PDFs, images, and media) into a queryable semantic graph, and ships as a `/graphify` skill for AI coding assistants (Claude Code, Cursor, GitHub Copilot, Gemini CLI, Codex, Antigravity, and others) alongside a `graphify` CLI.

This project (Manifest) is the system that manages and deploys AI-assistant configuration and supporting tools to a user's machine: it installs CLIs, deploys skills/configs across every enabled assistant, exposes per-service enable/disable toggles, verifies environment health, and documents the result. Integrating graphify means making it a **first-class managed tool inside that system** — installed, deployed, toggleable, verifiable, and documented through the same pipeline as every other managed service — rather than a tool a user installs by hand outside Manifest's control.

## Clarifications

### Session 2026-06-28

- Q: How should the `/graphify` skill be delivered to the AI assistants? → A: Vendor the skill into the project's single skill source of truth (`.skillshare/skills/`) and deploy it via the existing cross-assistant pipeline; do **not** use graphify's own installer for skill placement (avoids bypassing the source of truth and the FR-010 collision).
- Q: Should graphify be enabled by default or opt-in? → A: Enabled by default — installed and deployed on a standard setup run; operators opt out with `--disable-graphify` (behaves like the default-on core assistants).
- Q: How should the graphify CLI itself be installed during setup? → A: Manifest auto-installs the `uv` prerequisite when missing, then installs graphify, consistent with how setup already auto-installs Homebrew and Node.js.
- Q: What should graphify's default content-extraction backend be? → A: Local-first — code mapping with no credentials by default; reuse the project's already-configured Claude/Gemini auth for richer non-code extraction when present; never hard-fail setup on missing credentials.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Graphify is installed and available across assistants after setup (Priority: P1)

An operator runs the project's standard setup (graphify is enabled by default). When setup finishes, the graphify capability (its CLI and its `/graphify` skill) is installed and available in every assistant the operator has enabled, without any manual, out-of-band installation steps.

**Why this priority**: This is the core of the request — "integrated into the system the project provides." Without it, graphify is just an external tool the user installs themselves; with it, graphify is delivered by the same one-command setup that delivers every other capability. This story alone is a viable MVP.

**Independent Test**: Run setup on a clean machine, then confirm the `graphify` command is available and the `/graphify` skill appears in each enabled assistant.

**Acceptance Scenarios**:

1. **Given** a machine without graphify installed, **When** the operator runs the standard setup, **Then** the graphify capability is installed and the `/graphify` skill is available in every enabled assistant.
2. **Given** setup has already been run once, **When** the operator runs it again, **Then** graphify is not reinstalled or duplicated and the run completes without error (idempotent).
3. **Given** one or more assistants are disabled, **When** setup runs, **Then** the `/graphify` skill is deployed only to the assistants that are enabled.

---

### User Story 2 - Operators can opt out of graphify (Priority: P2)

An operator who does not want graphify (or its `uv`/graphify prerequisites) cleanly turns it off using the same `--disable-*` control every managed service offers, and that choice persists across setup runs.

**Why this priority**: Because graphify is enabled by default and pulls in an extra tool plus a `uv` prerequisite, operators must be able to opt out cleanly — consistent with the disable controls the system already offers for every service. Important, but the integration delivers value (Story 1) before this control matters.

**Independent Test**: Run setup with `--disable-graphify` and confirm graphify is not installed/deployed and no graphify credentials are requested; run again without the flag and confirm it is installed; verify the recorded preference survives a subsequent run.

**Acceptance Scenarios**:

1. **Given** the operator passes `--disable-graphify`, **When** setup runs, **Then** neither the graphify CLI nor its skill is installed or deployed, no `uv`/graphify prerequisite is added, and no graphify credentials are requested.
2. **Given** graphify was previously disabled, **When** the operator re-enables it and runs setup, **Then** graphify is installed/deployed and the preference is recorded for future runs.
3. **Given** a recorded graphify preference, **When** setup runs again without an explicit toggle, **Then** the previously recorded preference is honored.

---

### User Story 3 - Operators can verify and discover graphify through the system (Priority: P3)

After integration, the system's health/verification check reports graphify's status, and the project's documentation and command reference describe graphify the same way they describe every other managed capability.

**Why this priority**: Verification and documentation make the integration trustworthy and discoverable, but the capability is usable (Stories 1–2) before these are in place.

**Independent Test**: Run the environment health check and confirm graphify's install/availability status is reported; confirm the docs and command reference mention graphify and how to enable, use, and troubleshoot it.

**Acceptance Scenarios**:

1. **Given** graphify is enabled and installed, **When** the operator runs the environment health check, **Then** graphify is listed with an accurate available/authenticated status.
2. **Given** graphify is enabled but not yet installed, **When** the health check runs, **Then** it reports the specific gap (not installed) with actionable next steps. (Enriched-backend "not authenticated" reporting is deferred — see SC-004.)
3. **Given** a new contributor reads the project documentation, **When** they look for graphify, **Then** they find what it is, how to enable/disable it, how to invoke it, and how to troubleshoot it.

---

### Edge Cases

- **Prerequisite missing**: The `uv` installer graphify depends on is absent — setup installs it automatically; only if that auto-install itself fails does setup report a clear, actionable message and continue with the rest of the environment rather than aborting the whole run.
- **Offline / install failure**: The graphify package cannot be downloaded — the failure is surfaced clearly, does not corrupt the rest of the environment, and the run can be re-attempted.
- **Credentials absent for enriched content**: Graphify maps code locally without external credentials but needs a backend/credentials for non-code content (PDFs, images, media). When credentials are absent, the system communicates that graphify still works for code and explains how to enable the richer backends (reusing existing Claude/Gemini auth) — it does not hard-fail.
- **Assistant disabled**: An assistant the operator disabled must not receive the graphify skill.
- **Skill name collision**: The graphify skill must not overwrite or conflict with an existing managed skill of the same name; a collision is detected and surfaced rather than silently clobbering.
- **Partial enable**: Graphify enabled but an individual assistant's skill target is missing or not writable — deployment skips that target without failing the run, and the gap is observable through the system's existing health-check and config-sync symlink-integrity reporting (which surface graphify's presence/absence per assistant), rather than via bespoke per-target output.
- **Disable after enable**: Turning graphify off (`--disable-graphify`) on a machine where it was previously deployed leaves the environment in a clean, consistent state (no dangling skill entries for graphify).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST install the graphify capability (its CLI) as part of the standard setup flow when graphify is enabled. The system MUST ensure graphify's installation prerequisite (the `uv` Python tool installer) is present — installing it automatically if missing — before installing graphify, consistent with how setup already auto-installs other runtimes (Homebrew, Node.js).
- **FR-002**: The system MUST deploy the `/graphify` skill to every assistant that is enabled, so graphify is invocable inside each one, and MUST NOT deploy it to disabled assistants.
- **FR-003**: The system MUST expose enable and disable controls for graphify consistent with the existing per-service toggles (`--enable-graphify` / `--disable-graphify`), and MUST persist the operator's choice so it is honored on subsequent setup runs.
- **FR-004**: The system MUST enable graphify by default — installing and deploying it on a standard setup run — and MUST let operators opt out via `--disable-graphify`, mirroring the default-on core assistants (Cursor, Gemini, Codex, Antigravity).
- **FR-005**: Installation and deployment of graphify MUST be idempotent — re-running setup MUST NOT duplicate, corrupt, or repeatedly reinstall graphify or its `uv` prerequisite.
- **FR-006**: The system MUST handle a failed graphify installation (including a failed `uv` auto-install) gracefully — surfacing a clear, actionable message and continuing with the remainder of the environment rather than aborting the entire setup.
- **FR-007**: The environment health/verification check MUST report graphify's status (installed/available and, where applicable, authenticated) when graphify is enabled, including actionable guidance when a gap is detected.
- **FR-008**: The system MUST make graphify discoverable in the project's documentation and command reference — covering what it is, how to enable/disable it, how to invoke it, and how to troubleshoot it — to the same standard as other managed capabilities.
- **FR-009**: The graphify skill MUST be vendored into the project's single skill source of truth (`.skillshare/skills/`) and deployed through the existing cross-assistant deployment path, so it stays consistent across all assistant targets and is not hand-placed per assistant. The system MUST NOT rely on graphify's own installer to place the skill (which would bypass the source of truth and risk the FR-010 collision).
- **FR-010**: Graphify's deployment MUST NOT overwrite or collide with an existing managed skill or configuration of the same name; a collision MUST be detected and surfaced.
- **FR-011**: The system MUST default graphify to local-first extraction (code mapping that needs no external credentials) and MUST NOT hard-fail setup, nor block any default capability, because optional backend credentials are absent. (Graphify's default host-agent backend uses the running assistant session as the LLM, so no credentials are required by default.)
- **FR-011b** *(deferred — see SC-004)*: When optional enriched backends are later enabled, the system SHOULD reuse the project's already-configured assistant credentials (e.g., Claude/Gemini) rather than introducing a separate secret store, and SHOULD communicate clearly when a backend credential is needed. Enriched-backend support and its credential handling are out of baseline scope for this feature.
- **FR-012**: Disabling graphify MUST leave the environment in a clean, consistent state with no dangling graphify skill entries or configuration.

### Key Entities *(include if feature involves data)*

- **Graphify capability**: The managed tool being integrated — comprises a CLI and a `/graphify` skill. Attributes: enabled/disabled state, installation status, authentication/backend status.
- **Service toggle record**: The persisted operator preference for whether graphify is part of the environment, alongside the toggles for other managed services.
- **Skill artifact**: The `/graphify` skill definition vendored into the project's single skill source of truth (`.skillshare/skills/`) and deployed to each enabled assistant.
- **Assistant target**: An AI coding assistant (e.g., Claude Code, Cursor, Gemini, Codex, Antigravity) that, when enabled, receives the graphify skill.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a single standard setup run on a clean machine (graphify enabled by default), the graphify command is available and the `/graphify` skill is present in 100% of enabled assistants, with zero manual installation steps.
- **SC-002**: When the operator passes `--disable-graphify`, a setup run installs and deploys no graphify artifacts, adds no `uv`/graphify prerequisite, and requests no graphify credentials — a clean opt-out that leaves the rest of the environment unchanged.
- **SC-003**: Re-running setup produces no duplicate installs and no errors attributable to graphify (idempotent on the second and subsequent runs).
- **SC-004**: The environment health check reports graphify's status with 100% accuracy in the two states reachable under the default local-first (no-credential) configuration: *enabled-and-ready* and *enabled-but-not-installed*. (An *enabled-but-unauthenticated* state applies only if optional enriched backends — out of baseline scope, see Assumptions — are added later; detecting and testing it is explicitly deferred to that follow-up and is not part of this feature.)
- **SC-005**: A failure in graphify installation (e.g., offline or failed `uv` auto-install) never aborts setup of the rest of the environment — the remaining managed capabilities still complete successfully.
- **SC-006**: A new contributor can locate, enable/disable, invoke, and troubleshoot graphify using only the project documentation, without reading source.

## Assumptions

- **Scope is the project's own delivery system, not graphify's internals**: This feature wires graphify into Manifest's install/deploy/toggle/verify/document pipeline. It does not modify or fork graphify itself, and graphify's own graph-generation behavior is treated as a black box.
- **Enabled by default**: Graphify is integrated as a default-on managed service (like the core assistants), installed and deployed on a standard setup run; operators opt out with `--disable-graphify`. This changes default setup to include graphify and its `uv`/graphify prerequisites.
- **Skill delivered via the source of truth**: The `/graphify` skill is a Manifest-authored thin wrapper maintained in `.skillshare/skills/` (it shells the graphify CLI rather than vendoring upstream's multi-file skill), deployed by the existing pipeline; graphify's own installer is not used for skill placement. Upstream graphify changes are tracked manually, not auto-synced.
- **Existing patterns are reused**: Graphify uses the system's established mechanisms for CLI installation (auto-installing the `uv` prerequisite like Homebrew/Node), per-service toggles, cross-assistant skill deployment, health verification, and documentation — rather than introducing a parallel, graphify-specific pipeline.
- **All currently supported assistants are in scope**: Graphify's skill targets every assistant the system already manages and that graphify itself supports; assistants the operator has disabled are skipped.
- **Local-first backend**: Graphify defaults to local code mapping (no external credentials). Richer non-code extraction reuses the project's already-configured assistant credentials (Claude/Gemini) when present, rather than introducing a separate secret store or a setup-time credential gate.
- **Cross-platform parity**: Integration follows the system's existing macOS/Linux support; no new platform support is introduced by this feature.
