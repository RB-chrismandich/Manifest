# Contract: Verify-gate (smoke) + dual Spec-Review integration

**Feature**: 365-lifecycle-codification | Per research.md D6. The lifecycle **consumes** the smoke orchestrator and `spec_review.sh`; it does not modify the smoke runtime (FR-012).

## Contract 1 — Verify ↔ smoke orchestrator

Entry: `~/.claude/scripts/smoke_test.py` (repo `configs/claude/scripts/smoke_test.py`), `--catalog-dir smoke-catalog`, **one catalog file per unit** (`smoke-catalog/<unit>.yaml`).

### Implement phase (FR-008, author + record)
For each shipped user-facing workflow, the implementer authors/upserts a smoke test:
```
smoke_test.py append --from <workflow.json>     # idempotent upsert by id; exit 0 added/updated, 2 validation, 1 I/O
```
Critical-path workflows MUST be tagged **tier `Lite`** (cumulative selection excludes higher tiers from a `--tier Lite` gate).

### Implement-phase EXIT criterion (FR-008/010 — coverage reconciliation)
```
smoke_test.py list --app <unit> --json        # → [{id,tier,steps}, ...]
```
Compare the track's `shipped_workflow_ids` against the returned ids:
- every shipped id present in catalog → `coverage=OK`
- a shipped id absent AND not marked `exempt` in track state → `coverage=MISSING` → `decide` refuses advance (agent) / warns (human).
Exemptions live in **track state** (`subtask_states[...].exempt + exempt_reason`), not the catalog.

### Verify phase (FR-009/012 — the gate)
```
smoke_test.py run --app <unit> --tier Lite --junit <feature-dir>/verify-report.xml
```
Gate on **exit code** (authoritative): `0` PASS → allow · `1` FAIL/blocked → refuse(agent)/warn(human) · `2` EMPTY (no tests matched) → **refuse** (missing coverage ≠ pass, FR-010). Per-Sub-Task traceability (FR-011) reads JUnit `<testcase name=<workflow-id> classname=<unit>.<tier>>`.

**Do not** re-implement runner/tier/state logic — consume as-is (FR-012).

## Contract 2 — dual `/spec-review` (FR-002)

`spec_review.sh` today exposes only `--spec/--plan/--tasks/--silent/--format` and is **fail-open** (`main()` returns 0 regardless of findings). Two changes:

### Add `--mode product|technical`
- Thin sugar over the existing env seams `SPEC_REVIEW_TEMPLATE` (default `prompts/spec_review.md`) and `SPEC_REVIEW_STATE` (default `.spec-review`).
- `--mode product` → product-intent template + state dir `.spec-review/product`; `--mode technical` → technical/design template + `.spec-review/technical`.
- Default (no `--mode`) → **current behavior unchanged** (back-compat for existing callers + the save-hook).
- `--help` must list the flag and succeed before any dependency/state lookup (cli-help-before-dependency-checks); errors via `err()`.

### Parse verdict from JSON, not exit code
```
spec_review.sh --mode <m> --spec ... --plan ... --tasks ... --format json
```
- `[]` / `NO_ISSUES` → `APPROVED`
- non-empty findings → `NEEDS_REVIEW` (no blocking/critical) or `BLOCKED` (any critical/Tier-1) — severity from the finding payload.
- The phase maps this verdict through the constitution model (FR-027): `APPROVED`→allow, `NEEDS_REVIEW`→warn, `BLOCKED`→refuse.

### Optional consensus dimension (FR-027)
Because FR-001 allows one-or-more commands per phase, the review phase MAY also run `parallel_agent.py --validate` to obtain the Tier-1/Tier-2 + ≥80% consensus signal, combining it with the spec-review verdict (BLOCKED if either fails Tier-1).

## Deploy note
Repo `spec_review.sh` (parallel-agent panel) differs from the deployed `~/.claude/scripts/spec_review.sh` (older agy-only). The `--mode` change requires `./bootstrap.sh` redeploy before the lifecycle invokes the deployed path (known config-deploy gotcha).
