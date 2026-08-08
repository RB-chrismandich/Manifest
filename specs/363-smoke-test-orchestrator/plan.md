# Implementation Plan: Smoke Test Orchestrator

**Branch**: `363-smoke-test-orchestrator` | **Date**: 2026-06-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/363-smoke-test-orchestrator/spec.md`

## Summary

Deliver a declarative, config-driven E2E smoke-test system for the Manifest repo that an AI agent or CLI hook can drive: an **appender** turns a structured workflow description into tier-tagged YAML test definitions in a centralized per-app catalog, and an **executor** (Playwright Python) runs the catalog filtered by execution tier (`Lite`/`Full`/`Full+Extra`), passing state between chained steps and emitting a JUnit XML + console report with a gating exit code. Steps span three interaction types — UI (Playwright browser), API/HTTP (Playwright request context), and CLI/shell (subprocess) — so multi-language targets are all reachable by one engine. Secrets are never persisted: they are injected from the environment at run time and redacted from all output.

Delivered per the constitution's **Skill-First** principle: a thin `/smoke-orchestrator` skill is the agent-facing surface; the logic lives in a self-contained Python package with CLI entry points, not absorbed into `parallel_agent.py`.

## Technical Context

**Language/Version**: Python 3.12+ (repo CI standardizes on 3.14)

**Primary Dependencies**: Playwright (Python) — UI + API request context; PyYAML — catalog parse/emit; a small **internal validator** enforcing the vendored schema rules (no `jsonschema` runtime dep — keeps the footprint light and yields more actionable FR-003 errors); standard library `subprocess` — CLI/shell steps; JUnit XML emitted directly via stdlib `ElementTree`

**Storage**: YAML catalog files under `smoke-catalog/<app>.yaml` (committed, version-controlled config); persisted non-secret run state as JSON under the Manifest state root (`$MANIFEST_STATE_ROOT/smoke/state/`)

**Testing**: `pytest tests/python/` (engine unit + integration); `bats tests/bats/` for the CLI entry-point/skill wrapper; the orchestrator self-tests against a local fixture app

**Target Platform**: Linux (CI / ubuntu-latest) and macOS (developer machines)

**Project Type**: Single project — CLI tool + importable library, plus a skill wrapper

**Performance Goals**: A representative `Lite` run completes in < 2 minutes (SC-003) to serve as a PR gate; `Full`/`Full+Extra` run as nightly with no hard wall-clock cap

**Constraints**: Deterministic gate (no automatic step retry; FR-017); secret-safe (no secret persisted; env-injected + redacted; FR-013); concurrent-append safe per-app file (FR-015); cumulative tier selection (FR-006)

**Scale/Scope**: Tens of target applications × tens of tests each; chained steps within a test; not a high-throughput service

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Configuration-as-Code | PASS | Catalog (`smoke-catalog/*.yaml`), the skill, and Python package are version-controlled; appender edits committed YAML. No edits to deployed `~/.claude` files. |
| II. Parallel Agent Orchestration | GATE (deferred to PR) | This feature is **security-sensitive** (CLI/shell execution + secret handling) and exceeds 200 lines → Tier-1 cross-verification by ≥2 parallel agents (`parallel_agent.py`) is REQUIRED before merge. Recorded as an implementation-phase gate, not a planning blocker. |
| III. Consensus-Driven Decisions | GATE (deferred to PR) | The Tier-1 review at merge applies the ≥80% / 50–79% / <50% thresholds. |
| IV. Skill-First Extensibility | PASS | New capability ships as `.retired skill supply/skills/smoke-orchestrator/SKILL.md` invoking a discrete Python package; core scripts are not expanded to absorb it. |
| V. Bootstrap Reproducibility | PASS w/ note | The skill deploys via existing `bootstrap.sh` skill deployment. New runtime deps (Playwright + browser binaries) must be installed idempotently and gated by existence checks — see research R1. |

**Quality-gate alignment**: Tier-1 security (no shell injection in CLI steps, no secret leakage) and error-handling (no silent step failures) are first-class design concerns below. Tier-2 expects accompanying `pytest`/`bats` tests (Phase 1 contracts drive these).

**No unjustified violations.** Complexity Tracking table left empty.

**Post-Design Re-evaluation (after Phase 1)**: No new violations. The chosen structure keeps the engine in a discrete package behind a thin skill (IV); the Playwright/browser dependency is an idempotent opt-in extra (V, research R1); CLI steps use argument arrays with no `shell=True` and secrets are env-only + centrally redacted (Tier-1 security, research R2/R8). The only outstanding items are the **deferred merge-time gates** (II/III): the implementation PR must be cross-verified by ≥2 parallel agents via `parallel_agent.py` and clear the Tier-1 thresholds.

## Project Structure

### Documentation (this feature)

```text
specs/363-smoke-test-orchestrator/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── catalog.schema.json               # JSON Schema for a per-app YAML catalog
│   ├── workflow-description.schema.json   # Appender input contract
│   └── cli.md                            # CLI command contract (append/run/list)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
configs/claude/scripts/smoke_orchestrator/   # self-contained Python package
├── __init__.py
├── __main__.py            # `python -m smoke_orchestrator` dispatch
├── models.py              # dataclasses: Catalog, TestDefinition, Step, Tier, StateValue, RunReport
├── schemas/               # vendored JSON Schemas (copied from contracts/) for runtime validation
├── validation.py          # internal validator: validate_catalog / validate_workflow (enforces vendored schema rules, no jsonschema dep)
├── catalog.py             # load/validate/locate per-app YAML catalogs; atomic write + flock
├── appender.py            # SmokeTestAppender — idempotent append/update + file lock
├── redact.py              # Redactor — registers sensitive values, scrubs all output sinks
├── state.py               # StateManager — in-memory + persisted; secret-safe resolution
├── executor.py            # SmokeTestExecutor — Playwright UI/API + subprocess CLI, tier filter, chaining
├── steps/                 # one runner per interaction type
│   ├── ui.py              # browser steps (Playwright page)
│   ├── api.py             # HTTP steps (Playwright APIRequestContext)
│   └── cli.py             # shell steps (subprocess, arg-array, no shell=True)
├── report.py              # JUnit XML writer + console summary
└── cli.py                 # argparse entry: append | run | list | prune (--help, exit codes)

configs/claude/scripts/smoke_test.py          # thin executable shim → smoke_orchestrator.cli (chmod +x, --help)

.retired skill supply/skills/smoke-orchestrator/
└── SKILL.md               # agent-facing skill: when/how to append + run

smoke-catalog/                                 # centralized catalog root (committed)
└── <app>.yaml             # per-application test definitions

tests/python/smoke_orchestrator/
├── test_appender.py       # idempotency, validation, concurrent append
├── test_executor_tiers.py # cumulative tier selection, empty-selection, exit codes
├── test_chaining_state.py # in-memory + persisted state, blocked-downstream
├── test_secret_safety.py  # no secret in logs/report/state
└── fixtures/              # tiny local UI/API/CLI target + sample catalogs
tests/bats/
└── smoke_orchestrator_cli.bats   # CLI --help, exit codes, skill wrapper
```

**Structure Decision**: Single-project layout. The engine is a Python package under `configs/claude/scripts/` (where Manifest keeps its tooling), exposed through one executable shim (`smoke_test.py`) and one skill (`smoke-orchestrator`). The catalog lives at repo root `smoke-catalog/` so it is the obvious, centralized source of truth. This honors Skill-First (logic in a package, skill is the thin surface) and Config-as-Code (catalog + code committed).

## Architecture Overview (how an agent leverages the skill)

```text
 development lifecycle
 ─────────────────────
 1. Agent builds feature X ──▶ 2. Agent calls APPENDER with a structured
                                  workflow description (id, tier, steps, chaining)
                                          │
                                          ▼
                          SmokeTestAppender.append()
                          • validate vs workflow-description schema
                          • acquire per-app file lock
                          • upsert by stable id (idempotent)
                          • write smoke-catalog/<app>.yaml
                                          │
 3. CI / hook runs ───────────────────────▼
    `smoke_test.py run --app X --tier Lite`
                          SmokeTestExecutor.run(tier)
                          • cumulative tier filter (Lite ⊆ Full ⊆ Full+Extra)
                          • execute steps in authored order; validate each step's
                            `needs` are already satisfied (block if not) — no reordering
                          • per step: resolve ${state.*}/${env.*} refs (secret-safe)
                          •           dispatch to ui|api|cli runner under timeout
                          •           capture named outputs into StateManager
                          •           block downstream if required upstream state missing
                          • emit JUnit XML + console summary, set exit code
                                          │
 4. PR gate (Lite) / nightly (Full) consumes exit code + JUnit XML
```

The appender and executor are independently invocable (US1 vs US2 are separate MVP slices). The skill `SKILL.md` instructs an agent to call the appender right after it ships a feature, and to run the `Lite` tier as a gate.

## Complexity Tracking

> No constitution violations require justification. (Table intentionally empty.)
