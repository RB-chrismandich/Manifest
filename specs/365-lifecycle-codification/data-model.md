# Data Model: Codified State-Gated Development Lifecycle

**Feature**: 365-lifecycle-codification | **Date**: 2026-06-28
**Source**: spec.md Key Entities + research.md D1–D7. Storage per D2 (local JSON under `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/lifecycle/state/`, coarse status mirrored to tracker labels).

All persisted structures are JSON, written owner-only (`0700` dir / `0600` files), atomically, with secret redaction — reusing the smoke orchestrator `StateManager` pattern. The constitution/config-resident structures (Lifecycle Definition, Provider Mapping, Canonical-Status Map) are versioned in the repo, not in the state store.

---

## 1. Lifecycle Definition *(repo-resident; constitution + config)*

The canonical, ordered set of nine phases. Authoritative in the constitution ("Development Lifecycle" section); the machine-readable form drives `lifecycle.sh`.

| Field | Type | Notes |
|-------|------|-------|
| `phase_order` | int (1–9) | sequence position; gating compares these |
| `phase_id` | enum | `specify, clarify, spec_review_product, plan, task_creation, analyze, spec_review_tech, implement, verify` |
| `commands` | string[] | one **or more** ordered commands (FR-001) — e.g. `task_creation → [/speckit-tasks, /speckit-taskstoissues]` |
| `entry_criteria` | string | what must be true to begin (prior phase exit met) |
| `exit_criteria` | string | machine-checkable gate (e.g. verify → `smoke_test.py run` exit 0) |
| `artifacts` | string[] | files/entities produced/updated (e.g. specify → `spec.md`) |
| `gate_type` | enum | `verdict` (review/analyze, reuse APPROVED/NEEDS_REVIEW/BLOCKED), `coverage` (implement), `runner` (verify), `artifact` (others) |

**Validation**: `phase_order` contiguous 1–9; every phase has ≥1 command; `spec_review_product` and `spec_review_tech` both map to `/spec-review` but with distinct `--mode` (FR-002).

---

## 2. Lifecycle Track (Work Item) *(state store; one file per unit)*

The unit of work flowing through the lifecycle. **Anchored at the Task tier** (FR-028). File: `<provider>__<sanitized-entity-id>.json`.

| Field | Type | Notes |
|-------|------|-------|
| `track_id` | string | `<provider>__<entity-id>` |
| `entry_point` | object | `{raw, provider, entity_id, tier}` from the ticket URL/issue key (FR-019) |
| `tier_anchor` | enum=`task` | per FR-028, the track lives at Tier 3 |
| `current_phase` | enum (phase_id) | the single authoritative phase pointer |
| `completed_phases` | phase_id[] | append-only; gating reads this |
| `subtask_states` | map<subtask_id, {phase: implement\|verify, status, exempt, exempt_reason, coverage_workflow_ids[]}> | phases 8–9 iterate per Sub-Task (FR-028, FR-011) |
| `regression_log` | entry[] | `{from_phase, to_phase, reason, actor, ts}` (FR-005) — backward transitions only when logged |
| `actor_mode` | enum=`agent\|human` | drives hard-halt vs advisory (FR-004) |
| `shipped_workflow_ids` | string[] | user-facing workflows shipped in Implement; reconciled vs `smoke_test.py list --json` (FR-008/010) |
| `gate_results` | map<phase_id, GateResult> | last verdict per phase |
| `hierarchy_ref` | object | `{initiative, epic, task, subtasks[]}` of Hierarchy Node ids |
| `tracker_shadow` | object | `{last_synced_status, hash, ts}` for loop-safe reconciliation (D5) |
| `schema_version` | int | for forward migration |

**State transitions** (current_phase): strictly `phase_order n → n+1` only when phase `n` exit criteria pass (FR-004). Backward `n → m (m<n)` allowed only with a `regression_log` entry. Sub-task sub-states: `implement → verify` per Sub-Task; a Sub-Task is `done` only on a passing Verify (or recorded exemption).

**Validation**: `current_phase` ∈ Lifecycle Definition; no advance while any prior phase incomplete; a Sub-Task cannot reach `verify=passed` while `exempt=false` and its `coverage_workflow_ids` ∉ catalog.

---

## 3. Issue Hierarchy Node *(state store + tracker)*

An abstract tracked entity at one of four tiers, provider-independent (D4).

| Field | Type | Notes |
|-------|------|-------|
| `node_id` | uuid | local primary key |
| `external_id` | string | provider entity id/key (e.g. `PROJ-123`, `org/repo#42`) |
| `provider_type` | enum | `github\|gitlab\|linear\|jira` |
| `tier_level` | int (1–4) | Initiative/Epic/Task/Sub-Task |
| `parent_node_id` | uuid? | self-referential; null at Initiative |
| `status` | enum | one of the 4 canonical statuses |
| `provision_state` | enum | `present\|FAILED_PROVISION` (FR-016) |
| `remote_recorded_id` | string? | external id captured even on partial failure, for reconciliation |

**Validation/relationships**: a node's `parent` must be exactly one tier above (Sub-Task→Task→Epic→Initiative). Provisioning is **top-down** (parent `external_id` obtained before child creation). On partial failure: mark `FAILED_PROVISION`, record `remote_recorded_id`, halt children, flag for reconciliation — **no transactional remote delete** (D4/FR-016).

---

## 4. Provider Mapping *(config-resident)*

Translation between abstract tiers/statuses and a provider's native constructs (D4/D5). Lives in config (e.g. `configs/claude/config/lifecycle_providers.yml` + reuse `labels.yml`), **not** the constitution.

| Field | Type | Notes |
|-------|------|-------|
| `provider` | enum | github/gitlab/linear/jira |
| `tier_map` | map<tier_level, native_construct> | the D4 table row |
| `status_map` | map<canonical_status, label-or-transition> | labels (GH/GL/Linear) or Jira transition id |
| `missing_tier_behavior` | enum | `error` (default) or `collapse-to-label` (declared fallback) |
| `access` | enum | `cli` (gh/glab), `graphql` (linear_ops), `mcp` (jira) |

**Validation**: requesting a tier with no `tier_map` entry and `missing_tier_behavior=error` → configuration error naming the tier (FR-014). Jira `status_map` values must be transition ids, not free-text (FR-021).

---

## 5. Gate Result *(state store; embedded in Track)*

Outcome of a phase's exit criteria.

| Field | Type | Notes |
|-------|------|-------|
| `phase_id` | enum | which phase |
| `verdict` | enum | `APPROVED\|NEEDS_REVIEW\|BLOCKED` (review/analyze) · `PASS\|FAIL\|EMPTY` (verify) · `OK\|MISSING` (coverage) |
| `signal` | object | raw inputs — e.g. `{exit_code, junit_path}` for verify; `{findings_count, severity}` for spec-review |
| `decision` | enum | `allow\|warn\|refuse` (from `lifecycle.sh decide`) |
| `ts`, `actor` | string | audit |

**Validation**: verify `EMPTY` (exit 2) maps to `refuse` (missing coverage ≠ pass, FR-010); spec-review verdict parsed from `--format json`, **not** exit code (D6); `BLOCKED`/`FAIL`/`MISSING`/`EMPTY` → `refuse` for agents, `warn` for humans (FR-004).

---

## 6. Smoke Coverage Link *(state store; within `subtask_states`)*

Association between a user-facing Sub-Task and the smoke test(s) verifying it (FR-011).

| Field | Type | Notes |
|-------|------|-------|
| `subtask_id` | string | the Tier-4 node |
| `workflow_ids` | string[] | catalog test ids (per `smoke_test.py list --json`) |
| `exempt` | bool | true for non-user-facing Sub-Tasks |
| `exempt_reason` | string? | required when `exempt=true` |
| `tier` | enum=`Lite` | critical-path coverage must be Lite (D6) |

**Validation**: `exempt=false` ⇒ ≥1 `workflow_id` present in the catalog and passing at Lite; `exempt=true` ⇒ `exempt_reason` non-empty.

---

## 7. Entry Point *(transient; parsed into Track)*

The ticket URL / issue key that bootstraps a track (FR-019).

| Field | Type | Notes |
|-------|------|-------|
| `raw` | string | as provided |
| `provider` | enum | detected via pattern (extends `git_platform.sh`) |
| `entity_id` | string | extracted (`PROJ-123`, `org/repo#42`, Linear id) |
| `tier` | int (1–4) | classified from the entity's type/metadata |

**Validation**: an entry string matching no provider, or an unresolvable entity, → clear error and **no track created** (FR-019, edge case "Unrecognized entry point").

---

## Entity relationships (summary)

```
Lifecycle Definition (9 Phases)  ──drives──▶  lifecycle.sh decide/advance
                                                      │
Entry Point ──bootstraps──▶ Lifecycle Track ──anchored at──▶ Hierarchy Node(tier=Task)
                                  │                                  │ parent/child
                                  │ embeds                           ▼
                                  ├─▶ Gate Result (per phase)   Hierarchy Node(tiers 1,2,4)
                                  ├─▶ Smoke Coverage Link (per user-facing Sub-Task)
                                  └─▶ tracker_shadow ──reconciled via──▶ Provider Mapping ──▶ tracker labels / Jira transitions
```
