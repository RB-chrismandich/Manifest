# Contracts — Autonomous Issue Implementation Orchestrator

These JSON Schemas (draft 2020-12) are the **machine-parseable contract** between the orchestration daemon and the stateless decision engine. The daemon validates every engine response against `response-envelope.schema.json`, then validates `payload` against the matching phase schema. Validation failure is treated as a malformed engine response (retry under the FR-027 cap).

| File | Phase | Spec requirements |
|------|-------|-------------------|
| `response-envelope.schema.json` | all | FR-001–FR-007, FR-025, FR-035 |
| `phase1-prioritization.schema.json` | 1 | FR-008–FR-010, FR-036, FR-037 |
| `phase2-clarification.schema.json` | 2 | FR-011–FR-013, FR-028 |
| `phase3-tasking.schema.json` | 3 | FR-014–FR-016 |
| `phase4-analysis-gate.schema.json` | 4 | FR-017–FR-019, FR-028 |
| `phase5-verification-gate.schema.json` | 5 | FR-030–FR-033 |
| `phase6-pr-resolution.schema.json` | 6 | FR-020–FR-022 |

**Cross-cutting (not a payload schema, enforced in the daemon)**: FR-023 (untrusted input), FR-024 (no destructive ops), FR-029 (durable audit), FR-034 (gate consensus), FR-038 (redaction). These are verified by daemon-side tests, not by the payload schemas.

**Determinism note**: schemas use `additionalProperties: false` and fixed `required` ordering so that a conformant engine emits canonically-shaped output, supporting FR-003/SC-002.
