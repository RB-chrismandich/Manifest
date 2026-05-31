# Feature Specification: Parallel Agent Orchestration Modularization

**Feature Branch**: `001-modularize-parallel-agent`

**Created**: 2026-05-31

**Status**: Draft

**Input**: User description: "parallel_agent.py modularization — At 2145 lines / 74 functions it's past the point where a single file is maintainable. Natural split: agents/ package — config.py, runners.py, synthesis.py, validation.py, cli.py. Would make targeted tests and future changes much cleaner."

## Clarifications

### Session 2026-05-31

- Q: Should updating the test file's imports to match the new module structure be in scope for this feature? → A: Yes, in scope and required (FR-007 added; Assumptions corrected).
- Q: Are new per-module unit tests a required deliverable of this modularization? → A: Yes, required — new unit tests MUST ship alongside the restructuring (FR-008 added; SC-005 updated; Assumptions updated).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer Isolates a Code Concern (Priority: P1)

A developer needs to modify specific orchestration behavior — such as changing how
consensus is scored, updating validation rules, or adjusting agent timeout handling.
Currently, all logic lives in a single 2145-line file. The developer must search through
unrelated code to locate the relevant section, and any edit risks unintended side effects
in distant, intertwined functions.

After this feature, the developer opens the focused module for the concern they need to
change, reads a short file, makes the change confidently, and runs a targeted test to
verify.

**Why this priority**: This is the primary maintainability failure driving this work.
Locating and safely changing specific behavior is the most frequent developer activity,
and the current structure makes it risky and slow.

**Independent Test**: Can be fully tested by opening the split codebase, locating a
specific concern (e.g., consensus scoring logic), and verifying it resides in a single
focused module with no unrelated code. Delivers value independently of story 2 and 3.

**Acceptance Scenarios**:

1. **Given** the modularized codebase, **When** a developer needs to change how agent
   results are synthesized, **Then** they can find all relevant code in a single module
   of under 500 lines without reading unrelated concerns.

2. **Given** the modularized codebase, **When** a developer edits one module, **Then**
   the change does not require modifications to other modules unless a genuine interface
   boundary is crossed.

3. **Given** the modularized codebase, **When** any existing usage of the tool is
   re-executed, **Then** its behavior is identical to the pre-modularization version.

---

### User Story 2 - Developer Writes a Targeted Test (Priority: P2)

A developer wants to add or fix a test for a specific concern — for example, verifying
that consensus scoring correctly escalates below the 50% threshold, or that Tier 1
validation catches a missing error handler. Currently, testing any single concern
requires exercising the entire orchestration pipeline.

After this feature, the developer imports only the relevant module, constructs minimal
test inputs, and verifies the specific behavior without standing up the full multi-agent
pipeline.

**Why this priority**: Targeted tests catch regressions faster and give developers
confidence to make changes. Without them, the codebase becomes progressively harder to
evolve safely.

**Independent Test**: Can be fully tested by writing a new test that imports a single
module, exercises one function, and asserts a specific output — without requiring any
other module or external agent connection to be active.

**Acceptance Scenarios**:

1. **Given** the modularized codebase, **When** a developer writes a test for validation
   logic, **Then** they can import and instantiate only the validation module without
   pulling in agent runner or CLI dependencies.

2. **Given** the modularized codebase, **When** the test suite is run with a filter for
   a single module, **Then** only that module's tests execute and produce a meaningful
   pass/fail result.

3. **Given** the modularized codebase, **When** all existing tests are run, **Then**
   every test that passed before the modularization continues to pass.

---

### User Story 3 - Contributor Understands the Codebase (Priority: P3)

A new contributor wants to understand how the parallel agent orchestration works — how
agents are started, how their outputs are collected, and how consensus is reached. With
the current structure, they must read a 2145-line file with no clear entry points.

After this feature, the contributor reads the module index, picks the area they're
curious about, and reads a focused file that covers only that concern.

**Why this priority**: Contributor onboarding compounds over time — a more navigable
codebase attracts and retains contributors. This story delivers no user-visible behavior
change on its own.

**Independent Test**: Can be verified by asking a contributor unfamiliar with the code to
locate "where does consensus scoring happen?" and measuring whether they find it in under
two minutes using only the module structure (no grep).

**Acceptance Scenarios**:

1. **Given** the modularized codebase, **When** a contributor wants to understand
   configuration and model selection, **Then** they can read a single focused module that
   covers only that concern.

2. **Given** the modularized codebase, **When** a contributor wants to trace the flow
   from CLI invocation to agent output, **Then** they can follow a clear call path across
   modules without encountering unrelated implementation details.

---

### Edge Cases

- What happens when the entry point is invoked during a partial modularization (e.g., one
  module moved but another not yet)? Intermediate states MUST NOT be committed to the
  main branch.
- How does the system handle import errors if a module is missing or misconfigured?
  Existing error handling MUST be preserved.
- What happens to scripts or external callers that invoke the tool via its CLI interface?
  CLI behavior MUST remain unchanged — no caller should require modification.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The orchestration logic MUST be split into distinct modules, each with a
  single well-defined responsibility, covering at minimum: configuration/settings,
  agent execution, result synthesis, validation, and CLI interface.
- **FR-002**: The CLI interface MUST remain identical — all existing flags, arguments,
  output formats, and exit codes MUST be preserved without modification.
- **FR-003**: All tests that pass against the current codebase MUST continue to pass
  after modularization.
- **FR-004**: Each new module MUST be independently importable and testable without
  requiring the full orchestration environment.
- **FR-005**: The primary invocation method MUST continue to function as the entry point
  for all existing callers (scripts, CI workflows, user invocations).
- **FR-006**: No new user-facing capabilities are introduced by this change — scope is
  strictly structural reorganization.
- **FR-007**: Existing test files that import symbols directly from the orchestration
  script MUST be updated to reference the correct module locations after modularization,
  so that the full test suite remains executable without modification by the caller.
- **FR-008**: At least one new unit test file MUST be delivered for each new module,
  exercising the module's core behavior in isolation without requiring the full
  orchestration pipeline or external agent connections.

### Key Entities

- **Orchestration Entry Point**: The primary invocation method; must remain backward
  compatible with all existing callers.
- **Configuration Module**: All runtime settings, thresholds, model selection defaults,
  and parameter handling consolidated in one place.
- **Agent Runner Module**: Logic for executing individual agents, collecting their
  outputs, and managing timeouts or retries.
- **Orchestrator Module**: Coordination logic for running multiple agents concurrently,
  aggregating results, and scoring consensus across agent outputs.
- **Synthesis Module**: Logic for resolving agent disagreements and generating consensus
  reports when agreement falls below thresholds.
- **Validation Module**: The two-tier (Tier 1 blocking / Tier 2 advisory) quality gate
  checking logic applied to agent outputs.
- **CLI Module**: Argument parsing, help text, and the user-facing interface layer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can locate code for any specific concern (configuration, agent
  execution, synthesis, validation, CLI) within 2 minutes of opening the codebase using
  only the module structure — no text search required.
- **SC-002**: A developer can write a targeted test for any single concern without
  connecting to any external agent or running the full orchestration pipeline.
- **SC-003**: All existing end-to-end behaviors — multi-agent execution, consensus
  scoring, output format, exit codes — produce identical results before and after the
  change.
- **SC-004**: Each module introduced by this change contains fewer than 500 lines,
  making the entire concern readable in a single focused session. (`runners.py` and
  `orchestrator.py` are pre-approved exceptions per plan.md Complexity Tracking, due to
  class cohesion constraints; both are under 560 lines.)
- **SC-005**: Each new module ships with at least one dedicated unit test file that
  exercises its core behavior in isolation; test coverage for each module can be measured
  and reported independently of all other modules.

## Assumptions

- This is a pure structural refactoring — no new capabilities, flags, or output formats
  are introduced.
- CLI callers (shell scripts, CI workflows, documentation examples) invoke the tool via
  its CLI interface and do not require modification after modularization.
- The existing test suite imports symbols directly from the orchestration script as a
  Python module; updating these imports to match the new module structure is in scope
  for this feature (see FR-007).
- The five-concern split (configuration, agent execution, synthesis, validation, CLI)
  represents natural seams already present in the current codebase, based on the user's
  analysis.
- The entry point script remains the single invocation mechanism after modularization.
- Existing tests verify behavioral equivalence at the integration level; no new
  integration tests are required. New per-module unit tests are required deliverables
  (FR-008). Test file imports MUST be updated as part of this work (FR-007).
