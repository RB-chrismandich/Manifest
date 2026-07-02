# Feature Specification: Smoke Test Orchestrator

**Feature Branch**: `363-smoke-test-orchestrator`

**Created**: 2026-06-22

**Status**: Delivered 2026-06

**Input**: User description: "Declarative, config-driven E2E smoke test skill builder, hook-based test appender, and tiered workflow orchestrator that lets an AI agent automatically append, update, and iteratively chain end-to-end smoke tests for applications written in different languages whenever specific commands or skills run."

## Clarifications

### Session 2026-06-22

- Q: Declarative catalog format — YAML or JSON? → A: YAML (human-readable, comments allowed, consistent with the repo's existing config files).
- Q: Catalog organization — single file, per-app files, or per-test files? → A: One centralized directory with one file per application (`smoke-catalog/<app>.yaml`), for per-app isolation and low concurrent-append contention.
- Q: What machine-readable result artifact does the runner emit for CI? → A: JUnit XML (for CI annotations/dashboards) plus a human-readable console summary; the process exit code remains the gating signal.
- Q: Timeout/retry policy against live targets? → A: Bounded per-step timeout; no automatic retry by default (keeps the gate honest); retry is opt-in per step for legitimately async steps.
- Q: Tier inclusion semantics — cumulative, exclusive, or multi-tag? → A: Cumulative — a test's tier is its minimum inclusion level (`Lite` ⊆ `Full` ⊆ `Full+Extra`); tag once, broader runs are supersets.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent appends a smoke test when it ships a feature (Priority: P1)

When an AI agent (or a CLI hook) finishes building a new feature or skill, it describes the new user-facing workflow as structured data and hands it to the orchestrator. The orchestrator turns that description into one or more declarative test steps and merges them into the central smoke-test catalog, so test coverage grows in lockstep with the product without a human hand-authoring test scripts.

**Why this priority**: This is the core value proposition — keeping smoke coverage continuously synchronized with a fast-moving, multi-language codebase. Without it the rest of the system has nothing to run. It is independently valuable even if execution is done by an existing runner.

**Independent Test**: Provide the appender with a structured workflow description for a brand-new flow and confirm the central catalog gains a well-formed, tier-tagged test entry, existing entries are untouched, and the catalog still parses.

**Acceptance Scenarios**:

1. **Given** an empty or existing smoke-test catalog, **When** the agent submits a structured description of a new workflow, **Then** a new test with a unique identifier, a tier tag, and ordered steps is added and the catalog remains valid.
2. **Given** a catalog that already contains a test for the same workflow identifier, **When** the agent submits an updated description, **Then** the existing test is updated in place rather than duplicated.
3. **Given** a malformed or incomplete workflow description, **When** the agent submits it, **Then** the catalog is left unchanged and the agent receives an actionable validation error.

---

### User Story 2 - Run the suite filtered by execution tier (Priority: P1)

A pipeline, hook, or human runs the smoke suite selecting a tier: `Lite` for a fast critical-path gate that blocks a PR, `Full` for comprehensive nightly coverage, or `Full+Extra` for edge cases and deep validations. The runner executes only the tests tagged for that tier and returns a single pass/fail verdict plus a machine-readable exit code suitable for gating.

**Why this priority**: Tiering is what makes the same catalog usable both as a seconds-fast PR gate and as exhaustive nightly coverage. It is the other half of the MVP — an appender with no selective runner cannot gate anything.

**Independent Test**: Tag a catalog with a mix of `Lite`, `Full`, and `Full+Extra` tests, run with tier `Lite`, and confirm only `Lite` tests execute, the report lists per-test results, and the exit code is non-zero if and only if a selected test failed.

**Acceptance Scenarios**:

1. **Given** a catalog with tests across all three tiers, **When** the suite is run with tier `Lite`, **Then** only critical-path tests run and a higher tier's tests are excluded.
2. **Given** a selected tier in which every test passes, **When** the suite runs, **Then** the verdict is PASS with a zero exit code.
3. **Given** a selected tier in which at least one test fails, **When** the suite runs, **Then** the verdict is FAIL with a non-zero exit code and the failing test(s) are surfaced first.
4. **Given** a tier with no matching tests, **When** the suite runs, **Then** the result is reported as an empty selection (not a false pass) so the caller can tell coverage is missing.

---

### User Story 3 - Chain tests and pass state downstream (Priority: P2)

A workflow naturally spans steps: create a record, then read it, then act on it. The author marks a downstream step as depending on a value produced upstream (an id, token, or URL). During a run the orchestrator captures the upstream output and supplies it to the downstream step. The same value can optionally be persisted so a later, separate run (or a different tier) can reuse it.

**Why this priority**: Real E2E smoke flows are rarely single-shot; chaining is what distinguishes this from a list of isolated checks. It builds on US1/US2 and is high value but not required for a first usable gate.

**Independent Test**: Define a two-step chain where step A emits an identifier and step B references it; run the chain and confirm B receives A's actual runtime value, and that with persistence enabled the value is available to a subsequent independent run.

**Acceptance Scenarios**:

1. **Given** a chained test where a downstream step references a named value produced upstream, **When** the chain runs in a single pass, **Then** the downstream step receives the actual runtime value captured from the upstream step.
2. **Given** a downstream step whose required upstream value was never produced (upstream failed or was skipped), **When** the chain runs, **Then** the downstream step is reported as blocked/skipped — not silently passed and not run with a missing value.
3. **Given** persistence is enabled for a captured value, **When** a later independent run requests that value, **Then** the previously stored value is read and reused.

---

### User Story 4 - Lifecycle management of the catalog over time (Priority: P3)

As features change or retire, the catalog must be kept honest: re-appending the same workflow updates it, renamed or removed workflows can be pruned, and the catalog can be inspected to answer "what is covered, at what tier." This prevents the catalog from drifting into stale, duplicate, or orphaned tests.

**Why this priority**: Important for long-term trust in the suite but not needed to deliver initial value; it is a maintainability layer over US1–US3.

**Independent Test**: Append a workflow, append it again with changes, then list the catalog and confirm a single updated entry exists with correct tier and step count.

**Acceptance Scenarios**:

1. **Given** an existing test, **When** the same workflow identifier is appended with changes, **Then** the catalog shows one updated entry, not two.
2. **Given** a request to list coverage, **When** the catalog is inspected, **Then** each workflow's identifier, tier, and step count are reported.
3. **Given** a test that exists in the catalog, **When** it is pruned by identifier, **Then** only that test is removed and the catalog stays valid; pruning an identifier that is absent succeeds without changing the catalog.

---

### Edge Cases

- **Invalid input**: A workflow description missing required fields (identifier, tier, or at least one step) is rejected without mutating the catalog.
- **Duplicate identifiers**: Two tests cannot share an identifier; an append that would collide updates the existing test instead.
- **Unknown tier tag**: A test tagged with a tier outside the known set is surfaced as a configuration error rather than silently ignored.
- **Broken chain**: An upstream step fails midway — every downstream step depending on its output is marked blocked, and the run still produces a complete report.
- **Stale persisted state**: A persisted identifier no longer valid in the target environment must produce a clear failure on use, not a confusing downstream error.
- **Sensitive values**: When a captured/persisted value is a credential or token, it must not appear in logs, reports, or the catalog in readable form.
- **Concurrent appends**: Two agents appending at once must not corrupt the catalog or lose either change.
- **Empty selection**: Running a tier with zero matching tests is reported distinctly from "all tests passed."
- **Non-UI target**: A target application with no browser interface is smoke-tested via API/HTTP and/or CLI/shell steps rather than browser steps.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store smoke-test definitions in a single declarative, human-readable catalog that is independent of any target application's implementation language.
- **FR-002**: The system MUST expose a programmatic interface and a CLI entry point that accept a structured description of a new workflow and append it to the catalog as one or more ordered, tagged test steps.
- **FR-003**: The appender MUST validate every submitted workflow description against a defined schema and reject invalid submissions without modifying the catalog, returning an actionable error.
- **FR-004**: The appender MUST be idempotent per workflow identifier — re-submitting an existing workflow updates that test in place rather than creating a duplicate.
- **FR-005**: The system MUST support at least three execution tiers — `Lite` (critical-path PR gate), `Full` (comprehensive nightly), and `Full+Extra` (edge cases / deep validations) — assignable per test via metadata.
- **FR-006**: The runner MUST treat tiers as cumulative — a test's tier is its minimum inclusion level, so a requested tier runs every test at that tier and all lower tiers (`Lite` ⊆ `Full` ⊆ `Full+Extra`). A `Lite` run executes only `Lite` tests; a `Full` run executes `Lite` + `Full`; a `Full+Extra` run executes all.
- **FR-007**: The runner MUST produce a per-test pass/fail report and a single overall verdict, and MUST signal that verdict through a process exit code suitable for gating. Exit codes are defined as: **0** = all selected tests passed; **1** = at least one selected test failed or was blocked; **2** = empty selection (no tests matched) or a usage/configuration error. CI gates MUST treat any non-zero code as "do not merge." The runner MUST emit a machine-readable JUnit XML result file (for CI annotations and dashboards) alongside a human-readable console summary.
- **FR-008**: The runner MUST distinguish "no tests matched the selection" (exit **2**, verdict `EMPTY`) from "all selected tests passed" (exit **0**, verdict `PASS`), so that missing coverage is never reported as success. The appender uses an analogous scheme: **0** = appended/updated, **1** = I/O error, **2** = validation rejection (catalog unchanged).
- **FR-009**: The system MUST support test chaining in which a downstream step declares a dependency on a named value produced by an upstream step.
- **FR-010**: The system MUST provide a state manager that passes named values between steps in-memory during a single run and can optionally persist named values for reuse across separate runs.
- **FR-011**: When a downstream step's required upstream value is unavailable (upstream failed, was skipped, or was never produced), the system MUST mark that step blocked and MUST NOT run it with a missing value or report it as passed. A blocked step MUST count as a failure for the overall run verdict (contributing to a non-zero exit code per FR-007), and its own downstream dependents MUST cascade-block. The run MUST still complete and report every step.
- **FR-012**: The system MUST resolve references to captured, persisted, and environment values at run time, substituting the live value into the step before execution.
- **FR-013**: The system MUST keep sensitive captured values (credentials, tokens) out of logs, reports, and the catalog in readable form. Sensitive values MUST NOT be persisted: they are sourced from the environment at run time and redacted from all output. Only non-secret identifiers (ids, URLs) may be written to the persistent state store; a value flagged sensitive that lacks an environment source MUST fail clearly rather than fall back to persisting it.
- **FR-014**: The system MUST let an agent or operator inspect the catalog to report coverage (workflow identifier, tier, step count) without executing any tests.
- **FR-015**: The system MUST preserve the catalog's validity and the integrity of unrelated tests when concurrent or repeated appends occur.
- **FR-016**: The execution engine MUST support three step interaction types so that multi-language targets are all reachable by one engine: **browser/UI** interactions (for web front-ends), **API/HTTP** requests (for backend services without a UI), and **CLI/shell** invocations (for command-line tools). A single test MAY mix step types (e.g., an API step that creates a record feeding a UI step that displays it).
- **FR-017**: Every step MUST run under a bounded timeout and fail clearly when it is exceeded. The system MUST NOT retry a failed step automatically by default; retries are opt-in per step (with a bounded attempt count) for steps explicitly marked as async/eventually-consistent.
- **FR-018**: The system MUST support pruning a test from the catalog by its identifier. Pruning a present test removes only that test, leaving the rest of the catalog valid; pruning an absent identifier is idempotent (succeeds, catalog unchanged). Pruning does not modify other tests, so a removed test cannot silently break sibling tests; chaining is scoped within a single test, so no cross-test references are left dangling.

### Key Entities *(include if feature involves data)*

- **Smoke-Test Catalog**: The declarative source of truth — a centralized directory of per-application YAML files holding all test definitions; supports being read, validated, appended to, and updated.
- **Test Definition**: One named workflow — a stable identifier, a tier tag, an ordered list of steps, and optional chaining/state declarations.
- **Step**: A single declarative action within a test of one of three interaction types — **UI** (navigate/click/submit), **API/HTTP** (request/assert response), or **CLI/shell** (invoke command/assert output) — optionally producing a named output value and/or consuming named input values.
- **Tier**: A metadata classification (`Lite`, `Full`, `Full+Extra`) controlling when/whether a test runs and how it is selected.
- **State Value**: A named datum (id, token, URL, environment variable) captured from a step, scoped either to the current run (in-memory) or persisted for cross-run reuse, with a sensitivity flag.
- **Run Report**: The outcome of an execution — per-test status, captured-vs-missing state, overall verdict, and exit signal — emitted as both JUnit XML (CI-consumable) and a human-readable console summary.
- **Workflow Description**: The structured input an agent submits to the appender describing a new or changed flow to be turned into a Test Definition.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent can add coverage for a newly built workflow by submitting one structured description, with no manual editing of the catalog file, in a single step.
- **SC-002**: Re-submitting the same workflow ten times results in exactly one catalog entry (zero duplicates).
- **SC-003**: A `Lite` run executes only critical-path tests and completes fast enough to serve as a PR gate (target: under 2 minutes for a representative critical-path set), while a `Full` run covers the comprehensive set.
- **SC-004**: 100% of invalid workflow submissions are rejected without altering the catalog.
- **SC-005**: In a chained run, a downstream step uses the upstream step's real runtime value in 100% of successful chains, and 100% of downstream steps with missing required state are reported blocked rather than passed.
- **SC-006**: No sensitive value (token/credential) appears in any run log, report, or the catalog in readable form across the full test suite.
- **SC-007**: The same catalog is consumable as both a PR gate (`Lite`) and nightly coverage (`Full`) with no change other than the requested tier.
- **SC-008**: A coverage inspection reports every workflow's identifier, tier, and step count for the entire catalog.
- **SC-009**: The engine can smoke-test all three target shapes — a UI app, a UI-less HTTP service, and a CLI tool — from the same catalog using the appropriate step types.

## Assumptions

- **Centralized catalog**: "Centralized" is a single catalog directory holding one YAML file per target application (`smoke-catalog/<app>.yaml`). This keeps a single source-of-truth root while isolating each app's tests so concurrent appends from different agents touch different files (supporting FR-015).
- **Mandated technology**: The user requires the execution engine to be built in Python using Playwright (Python), with declarative test definitions in **YAML**. Playwright covers both UI and API/HTTP step types; CLI/shell steps are driven by Python subprocess execution. These are recorded as fixed constraints for the planning phase; they do not change the user-facing behavior described above.
- **Agent-driven authorship**: Tests are primarily authored by AI agents/hooks via the structured appender interface; direct hand-editing of the catalog remains possible but is not the primary path.
- **Target reachability**: Target applications are reachable from the run environment via a configured base location (URL/endpoint); provisioning the targets themselves is out of scope.
- **Tier inclusion**: Tiers are cumulative (confirmed): a test's tier is its minimum inclusion level, so `Full` includes `Lite` and `Full+Extra` includes `Full`. Each test is tagged once at its lowest applicable tier.
- **Chaining failure semantics**: A blocked downstream step (missing upstream state) is treated as a failure for gating purposes, not a pass — now formalized in FR-011.
- **Execution environment**: Runs happen in CI and on developer machines; the persistence layer defaults to the Manifest state root for local/persisted identifiers.
- **Out of scope for v1**: Load/performance testing, visual-regression/pixel diffing, and self-healing selectors — this feature targets functional smoke coverage only.

## Dependencies

- A declarative-config parser and a browser/automation execution capability (mandated: Playwright Python).
- The hook/skill invocation surface that lets agents call the appender when a feature or skill runs.
- A writable state location for persisted identifiers (defaults to the Manifest state root).
