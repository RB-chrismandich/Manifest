# Phase 1 Data Model: Autonomous Issue Implementation Orchestrator

**Date**: 2026-06-14 | **Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Entities are drawn from the spec's Key Entities plus the implementation-derived state objects from research (R4, R9). "Engine-visible" entities cross the daemon↔engine boundary as JSON; "Daemon-only" entities never reach the stateless engine.

---

## Engine-visible entities (cross the JSON boundary)

### Issue
The unit of work being driven.

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | Required; tracker-native identifier (e.g., `#123`, `gl!45`). |
| `title` | string | Required. |
| `body` | string | Untrusted data (FR-023); never interpreted as instructions. |
| `labels` | string[] | Includes `no-automation` when the kill-switch is active (FR-037). |
| `severity` | enum `critical\|high\|medium\|low` | Derived metadata-first; inferred from `body` only if absent (FR-036). |
| `severity_source` | enum `label\|field\|inferred` | Required; recorded in reasoning trace (FR-036). |
| `depends_on` | string[] | Other issue ids this one depends on; drives Phase 1 unblock ranking (FR-009). |

**Validation**: an Issue bearing `no-automation` MUST NOT be selected/advanced (FR-037). Dependency graph MUST be checked for cycles (edge case).

### Context Payload (daemon → engine)
The complete per-invocation input; the engine holds no other state (FR-006).

| Field | Type | Rules |
|-------|------|-------|
| `phase` | int 1–6 | Required; the `[CURRENT PHASE]` directive. |
| `inputs` | object | Phase-specific parsed tool outputs (issues, speckit output, analysis, verification, PR feedback). |
| `attempt` | int ≥1 | Per-phase attempt count for the FR-027 cap. |
| `consensus` | object\|null | Present at gates: agent verdicts to aggregate (FR-034). |
| `critical_failure` | bool | Daemon-set; forces `needs_escalation` (FR-025). |
| `resource_available` | bool | False when agents are token/credit-exhausted (FR-035). |

### Response Envelope (engine → daemon)
The single top-level object every invocation returns (FR-001). See `contracts/response-envelope.schema.json`.

| Field | Type | Rules |
|-------|------|-------|
| `phase` | int 1–6 | Echoes the directive. |
| `status` | enum `ok\|blocked\|needs_escalation` | FR-001. |
| `payload` | object | Phase-specific; `{}` when `status≠ok` (FR-005). |
| `reasoning_log` | string[] | Ordered decision trace; all justification here only (FR-004); redacted before persistence (FR-038). |
| `escalation` | object\|null | `{reason, blocking_state}`; `blocking_state.transient=true` for resource pauses (FR-035). |

**Validation**: exactly one envelope, nothing outside it (FR-002); deterministic field ordering (FR-003); on missing/contradictory input → `blocked` + empty payload + populated escalation (FR-005).

### Phase-specific payloads
One schema per phase under `contracts/` (see contracts README):

- **Phase 1 — Prioritization**: `{ranked_issue_ids[], top_choice_justification, dependency_notes[]}`.
- **Phase 2 — Clarification synthesis**: `{finalized_spec_parameters{}, agy_conflicts[], open_questions[]}`.
- **Phase 3 — Tasking**: `{tasks[]}` where each task has `{seq, title, description, acceptance_criteria[], speck_review_criteria_addressed[], depends_on[]}` (FR-014–FR-016).
- **Phase 4 — Analysis gate**: `{gate: clean\|blocked, required_fixes[], implement_approved}` (FR-017–FR-019, FR-028).
- **Phase 5 — Verification gate**: `{verdict: verified\|blocked, dimensions{design_intent,functionality,standards}, tier1_findings[], tier2_findings[], pr_open_approved}` (FR-030–FR-033).
- **Phase 6 — PR resolution**: `{modifications[], pr_reply, ci_root_cause}` (FR-020–FR-022).

### Supporting engine-visible objects

- **Task** — fields per Phase 3 payload; every task independently verifiable with named acceptance criteria (FR-015).
- **Analysis Finding** — `{severity: error\|warning\|regression, file?, fix_directive}`; any finding blocks the pre-impl gate (FR-017, fail-closed FR-019).
- **Verification Result** — `{verdict, findings[] each {dimension, tier: 1\|2, detail, remediation?}}`; Tier 1 blocks PR-open, Tier 2 advisory (FR-031). An unmet acceptance criterion is a Tier 1 finding (FR-032).
- **Recommendation (agy)** — advisory Phase-2 input; absence does not block (FR-028 exemption).
- **PR Feedback Item** — `{source: review\|ci, ref, detail}` → one or more Modifications.
- **Consensus Result** — `{agreement_ratio, band: high\|medium\|low, votes[], disagreements[]}`; maps to auto-proceed / proceed-with-flags / escalate (FR-034).
- **Escalation** — `{reason, blocking_state{type, transient}}`; `transient=true` ⇒ pause-and-resume, not human escalation (FR-035).

---

## Daemon-only entities (never reach the engine)

### Pipeline Run State (per-run JSON file, R9)

| Field | Type | Rules |
|-------|------|-------|
| `run_id` | string | Required; unique per pipeline run. |
| `selected_issue` | string | Issue id chosen in Phase 1. |
| `current_phase` | int 1–6 | Working cursor. |
| `attempt_counts` | map<phase,int> | Drives FR-027 2-attempt cap. |
| `last_status` | enum | Mirrors last envelope status. |
| `paused` | bool | True during resource-pause (FR-035); resumes without incrementing attempts. |

### Audit Record (append-only JSONL line, R4)
`{run_id, phase, status, payload, reasoning_log, escalation}` — `payload` is included so the per-phase decision content (ranked ids, tasks, verdict, modifications, pr_reply) is recoverable (SC-010). Written after **mandatory redaction** (FR-038); fail-open for observability.

---

## Pipeline state machine

```text
            ┌─────────────────────────────── no-automation label present at any advance ──────────────────────────────┐
            │                                                                                                          ▼
SELECT (P1) ──► CLARIFY (P2) ──► PLAN/TASK (P3) ──► ANALYSIS GATE (P4) ──► [implement] ──► VERIFY GATE (P5) ──► PR OPEN ──► REVIEW/RESOLVE (P6) ──► CLEAN PR
   │                │                  │                  │ clean                              │ verified                          │
   │                │                  │                  │                                    │                                   │
   └── empty/all-held ──► HELD         └── gate blocked ──┘ (fixes, re-attempt ≤2)              └── Tier1 blocked ──► (remediate,    └── CI/review feedback loop
                                                                                                     re-attempt ≤2)
Transitions common to every phase:
  • attempt == 2 and phase fails        ──► ESCALATE (needs_escalation)         (FR-027)
  • resource_available == false         ──► PAUSE (transient) ──► resume same phase, no attempt++  (FR-035)
  • critical_failure flag               ──► ESCALATE                            (FR-025)
  • consensus band == low (<50%) at gate ──► ESCALATE                           (FR-034)
  • missing/contradictory input          ──► BLOCKED + escalation               (FR-005)
```

**Terminal states**: `CLEAN PR` (success), `HELD` (kill-switch or no implementable work), `ESCALATE` (human handoff). `PAUSE` is non-terminal (always resumes).
