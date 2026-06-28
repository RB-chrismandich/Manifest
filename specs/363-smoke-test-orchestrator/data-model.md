# Phase 1 Data Model: Smoke Test Orchestrator

Entities derive from the spec's Key Entities, with fields/validation from the Functional Requirements. Python representation: frozen `@dataclass` where practical; YAML on disk; JSON Schema in `contracts/`.

## Catalog (per application)

One YAML file `smoke-catalog/<app>.yaml`. The centralized catalog is the directory of these files (clarified Q2).

| Field | Type | Rules |
|-------|------|-------|
| `version` | int | Schema version; currently `1`. Unknown major → load error (forward-compat guard). |
| `app` | string | Application/namespace id; MUST equal the file stem. Slug `^[a-z0-9][a-z0-9-]*$`. |
| `base_url` | string (optional) | Default target base for UI/API steps; overridable per step. |
| `tests` | list[TestDefinition] | Unique by `id`. May be empty. |

## TestDefinition

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | Stable slug, unique within the app file. The idempotency key (FR-004). `^[a-z0-9][a-z0-9-]*$`. |
| `title` | string | Human label. |
| `tier` | enum | `Lite` \| `Full` \| `Full+Extra`. Minimum inclusion level (FR-006). Unknown value → config error (FR-005 edge case). |
| `steps` | list[Step] | ≥1 (FR-003 rejects empty). Executed in listed order, subject to `needs`. |
| `tags` | list[string] (optional) | Free-form filters (e.g., `smoke`, `auth`). |

## Step

Discriminated by `type` (FR-016).

| Field | Type | Applies to | Rules |
|-------|------|-----------|-------|
| `name` | string | all | Unique within the test; referenced by `needs`. |
| `type` | enum | all | `ui` \| `api` \| `cli`. |
| `action` | string | ui | e.g., `goto`, `click`, `fill`, `expect_text`. |
| `selector` / `value` | string | ui | Target + optional input; may contain `${...}` refs. |
| `method` / `path` / `body` | string/obj | api | HTTP verb, path (joined to `base_url`), optional payload. |
| `expect_status` | int (optional) | api | Asserted status; default 2xx. |
| `command` | list[string] | cli | **Argument array only** (R2 security); each element may contain `${...}` refs resolved into that element. |
| `expect_exit` | int (optional) | cli | Default `0`. |
| `captures` | map[name → extractor] | all (optional) | Stores named outputs into state. Extractor is JSONPath (api), selector/attr (ui), or regex group (cli). |
| `needs` | list[string] (optional) | all | Capture names this step requires; missing → step blocked (FR-011). |
| `timeout_ms` | int (optional) | all | Per-step bound; default from runner config (FR-017). |
| `retry` | object (optional) | all | `{attempts: int}` — opt-in only; absent ⇒ no retry (FR-017). |
| `sensitive` | bool (optional) | all | If a capture is sensitive, it resolves from `${env.*}` only and is never persisted (FR-013). |

## Tier (value object)

Ordered enum: `Lite (0) < Full (1) < Full+Extra (2)`. Selection predicate: `test.tier_rank <= requested.tier_rank` (R6).

## StateValue

| Field | Type | Rules |
|-------|------|-------|
| `name` | string | Reference key used in `${state.<name>}`. |
| `value` | any | Captured runtime datum (id/url/token). |
| `scope` | enum | `run` (in-memory only) \| `persisted` (written to state store). |
| `sensitive` | bool | If true → MUST NOT be persisted; env-sourced; redacted (FR-013). |

**State store** (persisted scope only): `$MANIFEST_STATE_ROOT/smoke/state/<app>.json`, holding only non-secret values.

## RunReport

| Field | Type | Rules |
|-------|------|-------|
| `app` | string | |
| `tier` | enum | Requested tier. |
| `results` | list[TestResult] | Per test: `status ∈ {passed, failed, blocked}`, duration, message (redacted). |
| `selected` | int | Count of tests selected; `0` ⇒ empty-selection state (FR-008), distinct from all-passed. |
| `verdict` | enum | `PASS` \| `FAIL` \| `EMPTY`. |
| `exit_code` | int | `0` pass, `1` fail/blocked, `2` empty-selection/usage error. |
| Outputs | files | JUnit XML at `--junit <path>` + console summary. |

## WorkflowDescription (appender input)

The structured object an agent submits (contract: `contracts/workflow-description.schema.json`).

| Field | Type | Rules |
|-------|------|-------|
| `app` | string | Target catalog file (created if absent). |
| `id` | string | Stable slug; upsert key. |
| `title`, `tier`, `steps` | as TestDefinition | Validated before write (FR-003); invalid ⇒ no mutation + actionable error. |

## State transitions

```text
TestDefinition lifecycle (in catalog):
  (absent) ──append(new id)──▶ present
  present  ──append(same id)─▶ present (updated in place; never duplicated)   [FR-004]
  present  ──prune(id)───────▶ (absent)                                       [US4]

Step execution (per run):
  pending ──needs satisfied & passes──▶ passed
  pending ──needs satisfied & fails───▶ failed   (downstream dependents ─▶ blocked)
  pending ──needs missing─────────────▶ blocked  (cascades to its dependents) [FR-011]
```

## Validation rules (enforced by appender & loader)

- Reject: missing `id`/`tier`/`steps`, empty `steps`, unknown `tier`, duplicate `name` within a test, `cli` `command` that is not a list, capture/needs name mismatch.
- A `sensitive` ref with no `${env.*}` source ⇒ hard error (no plaintext fallback) (FR-013).
- `app` field MUST match the file stem (prevents cross-app writes).
