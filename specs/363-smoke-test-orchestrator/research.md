# Phase 0 Research: Smoke Test Orchestrator

All Technical Context unknowns are resolved below. Spec-level decisions (YAML format, per-app catalog, JUnit XML, no-auto-retry, cumulative tiers, secret-never-persisted) were fixed during `/speckit-clarify` and are treated as inputs, not open questions.

## R1 — Playwright runtime + browser binaries in CI/bootstrap

- **Decision**: Make the orchestrator's dependencies an **opt-in extra**, installed only when smoke is enabled. Add a `requirements-smoke.txt` (playwright, pyyaml, jsonschema) and install Chromium only (`playwright install chromium`) — not all browsers. Gate install behind an existence check (`playwright --version` / browser cache present) so re-runs are idempotent (Constitution V).
- **Rationale**: Browser binaries are ~hundreds of MB; installing all three on every machine violates the "fast, idempotent bootstrap" contract. Chromium alone covers UI smoke; API and CLI steps need no browser at all, so a Chromium-less environment can still run API/CLI tiers.
- **Alternatives considered**: (a) Bundle Playwright in the default bootstrap — rejected: heavy, slows every install. (b) Selenium — rejected: heavier driver management, no unified API request context. (c) Requests/httpx for API + Playwright for UI — rejected: two HTTP stacks; Playwright's `APIRequestContext` shares cookies/auth with the browser context, which chained UI→API flows benefit from.

## R2 — One engine, three interaction types

- **Decision**: A `Step.type ∈ {ui, api, cli}` discriminator dispatches to a dedicated runner. UI → Playwright `Page`; API → Playwright `APIRequestContext`; CLI → `subprocess.run` with an **argument list** (never `shell=True`).
- **Rationale**: A single discriminated step keeps the YAML uniform while letting non-UI multi-language targets (backend services, CLI tools) be smoke-tested. Sharing one Playwright `BrowserContext` lets a UI login seed the API request context's auth.
- **Alternatives considered**: Separate catalogs per interaction type — rejected: breaks chaining across types (FR-016 allows mixed-type tests) and complicates the appender.
- **Security note (Tier-1)**: CLI steps MUST pass `args: [..]` arrays, reject a single string command, and never interpolate resolved state into a shell string. State substitution happens into discrete arg elements after splitting, so a token value can never inject a second command.

## R3 — JUnit XML emission

- **Decision**: Hand-write JUnit XML with `xml.etree.ElementTree` (stdlib). One `<testsuite>` per catalog/app, one `<testcase>` per test definition; `<failure>` for fails, `<skipped>` for blocked-downstream and empty-selection markers. Also print a human console summary table.
- **Rationale**: The JUnit subset CI consumes (GitHub Actions test annotations, dashboards) is tiny and stable; a stdlib writer avoids adding `junit-xml`/`junitparser` as a runtime dependency (lighter, fewer supply-chain surfaces).
- **Alternatives considered**: `junitparser` library — rejected: unnecessary dependency for ~30 lines of XML. Emitting only JSON — rejected: most CI dashboards expect JUnit (clarified Q3).

## R4 — State-reference templating & resolution

- **Decision**: References use `${state.<name>}` (captured/persisted run state) and `${env.<NAME>}` (environment). Resolution is a single pass over a step's declared fields just before execution. A `captures:` block on a step names outputs to store (e.g., `order_id: "$.id"` JSONPath for API, a selector/text extractor for UI, a regex/stdout group for CLI).
- **Rationale**: `${...}` namespacing makes secret vs non-secret origin explicit (`env.*` is the only path for secrets; see R8) and keeps the YAML readable. JSONPath/selector/regex capture covers the three step types uniformly.
- **Alternatives considered**: Jinja2 templating — rejected: too powerful (arbitrary expressions) for a declarative gate and a larger dependency/attack surface. Positional chaining (step N output → step N+1 input) — rejected: brittle when steps are reordered; named refs are explicit (clarified during /specify chaining design).

## R5 — Idempotent append & concurrent-write safety

- **Decision**: `SmokeTestAppender` keys tests by a stable `id` (slug). Append = load → upsert-by-id → atomic write (`tempfile` + `os.replace`). Concurrency is guarded by an OS advisory file lock (`fcntl.flock`) on the per-app catalog file; per-app files (clarified Q2) mean different apps never contend.
- **Rationale**: Upsert-by-id gives idempotency (FR-004, SC-002: 10 appends → 1 entry). Atomic replace prevents a partial/corrupt catalog if interrupted. `flock` + per-app files make concurrent appends from different agents safe (FR-015).
- **Alternatives considered**: Append-only with later dedup — rejected: violates idempotency and bloats diffs. Global single-file lock — rejected: serializes all agents; per-app files already isolate contention.

## R6 — Cumulative tier model

- **Decision**: Each test carries one `tier` = its minimum inclusion level. Selection: `requested ∈ {Lite, Full, Full+Extra}` runs every test whose tier is ≤ requested in the order `Lite < Full < Full+Extra`. "No tests matched" is a distinct exit state (FR-008), not a pass.
- **Rationale**: Tag-once authoring; critical-path (`Lite`) tests can never be accidentally dropped from a broader run (clarified Q5). Matches FR-006.
- **Alternatives considered**: Exclusive tiers / multi-tag — rejected in clarification (duplication / verbosity).

## R7 — Chaining order & blocked-downstream

- **Decision**: Within a test, steps are ordered; a step may declare `needs: [<capture names>]`. Before running a step, the executor checks all `needs` are present in `StateManager`; if any is missing (upstream failed/skipped), the step is marked **blocked** (JUnit `<skipped>` + counts as a gating failure of that test, per spec Assumptions), and its own downstream dependents cascade-block. The run always completes and reports every step.
- **Rationale**: FR-011 — never run a step with missing state, never silently pass it. Cascade-block keeps the report truthful without aborting the whole suite.
- **Alternatives considered**: Abort test on first missing state — rejected: loses report completeness for sibling steps. Treat blocked as pass — rejected: explicitly forbidden (FR-011).

## R8 — Secret handling (env-injected, never persisted, redacted)

- **Decision**: A captured/declared value may be flagged `sensitive: true`. Sensitive values resolve **only** from `${env.*}` at run time; they are never written to persisted state or the catalog. A central `Redactor` holds the set of resolved sensitive values and scrubs them from all log lines, JUnit `<failure>` text, and console output before emit. A `sensitive` ref with no env source raises a clear error (no plaintext fallback).
- **Rationale**: FR-013 / SC-006 — zero secret leakage. Centralizing redaction at the output boundary means every sink is covered by construction.
- **Alternatives considered**: Encrypt-at-rest persistence — rejected in clarification (key-management burden). Plaintext local state — rejected (commit/leak risk).

## Resolved unknowns summary

| Unknown (from Technical Context) | Resolution |
|----------------------------------|------------|
| Playwright/browser install footprint | R1 — opt-in extra, Chromium-only, idempotent |
| Unifying UI/API/CLI | R2 — discriminated step + shared context; subprocess arg-arrays |
| JUnit emission without new dep | R3 — stdlib ElementTree writer |
| State templating syntax | R4 — `${state.*}`/`${env.*}` + typed captures |
| Idempotent + concurrent append | R5 — upsert-by-id, atomic replace, per-app flock |
| Tier selection rule | R6 — cumulative |
| Chaining failure semantics | R7 — blocked + cascade, full report |
| Secret safety | R8 — env-only, never persisted, central redactor |
