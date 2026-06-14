# Implementation Plan: Autonomous Issue Implementation Orchestrator

**Branch**: `004-autonomous-issue-orchestrator` | **Date**: 2026-06-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-autonomous-issue-orchestrator/spec.md`

## Summary

A long-running **orchestration daemon** drives one selected GitHub/GitLab issue at a time through six phases — ingestion & prioritization, dual-model clarification synthesis, planning & tasking, pre-implementation analysis gate, post-implementation verification gate, and code review & PR resolution — to a clean, review-ready Pull Request, with no human gate before PR-open. The daemon owns all execution, Git/API calls, polling, timeouts, and audit persistence; the **decision logic is a stateless engine** invoked once per phase that returns a single machine-parseable JSON envelope (phase, status, payload, reasoning trace, escalation) and is fully deterministic.

Technical approach: implement the daemon as a **new standalone Python runner** under `configs/claude/scripts/` that *composes* existing infrastructure rather than absorbing logic into it — `parallel_agent.py` for gate cross-verification and consensus scoring (Principle II/III), `git_ops.sh`/`git_platform.sh` for platform-agnostic issue/PR operations, `skillclaw_audit.py`'s JSONL append-only pattern for the durable audit trail (FR-029), and `skillclaw_scrub.py`'s redaction for secret/PII masking (FR-038). The per-phase decision contracts are expressed as **skills** (Principle IV: Skill-First Extensibility) plus versioned JSON Schemas under `contracts/`. Consensus thresholds, retry caps, the hourly resource-pause poll, and redaction patterns are configured in a new `configs/claude/config/orchestrator.yml` (Principle I: Config-as-Code); the `no-automation` kill-switch label is added to `labels.yml`.

## Technical Context

**Language/Version**: Python 3.11+ (daemon + decision-engine adapters), Bash 3.2+ (git/PR operation wrappers, reused). Matches `parallel_agent.py` and existing `configs/claude/scripts/` conventions.

**Primary Dependencies**: Existing repo scripts — `parallel_agent.py` (cross-verification/consensus), `git_ops.sh` + `git_platform.sh` (issue/PR/platform), `skillclaw_audit.py` (audit pattern), `skillclaw_scrub.py` (redaction). External CLIs invoked by the daemon (not the engine): `gh`/`glab`, `speckit` (`specify`/`clarify`/`plan`/`tasks`/`analysis`/`implement`), `agy`. Config via PyYAML (already used). No new third-party runtime deps preferred.

**Storage**: Append-only JSONL audit log on the local filesystem under a `chmod 700` state directory (e.g., `~/.claude/state/orchestrator/audit-<run>.jsonl`), following the `skillclaw_audit.py` precedent. Per-run pipeline state (current phase, attempt counts, selected issue) persisted as JSON so the stateless engine can be re-invoked deterministically. No database.

**Testing**: `pytest tests/python/` (daemon, engine adapters, redaction, consensus mapping, audit) and `bats tests/bats/` (CLI entry points, `--help`, label sync). Lint: `shellcheck` (shell), `yamllint` (YAML), per the constitution's Development Workflow.

**Target Platform**: macOS (Intel/Apple Silicon) and Linux, consistent with `bootstrap.sh` supported platforms. CLI/daemon process; no GUI.

**Project Type**: Single project — a CLI/daemon plus supporting skills and config, deployed via `bootstrap.sh` into `~/.claude/`.

**Performance Goals**: Median small-scope issue from selection to opened PR within **30 min of active processing**, excluding human-review and resource-pause waits (SC-017). Each engine decision returns promptly (single LLM invocation per phase); gate phases add bounded multi-agent cross-verification latency.

**Constraints**: Stateless decision engine (all state in the context payload); 100% deterministic, single-envelope JSON output (FR-001–FR-007); fail-closed pre-implementation gate and Tier-1 fail-closed verification gate; secret/PII redaction before any durable write; 2-attempt per-phase cap with token-exhaustion pause excluded; idempotent install/config (Principle V).

**Scale/Scope**: One active issue per pipeline run (concurrency deferred). Backlog sizes typical of a single repository (tens to low-hundreds of open issues for prioritization). Six phases; 38 functional requirements; 17 measurable outcomes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|------------|--------|
| **I. Configuration-as-Code** | All orchestrator config lives in `configs/claude/config/orchestrator.yml` + `labels.yml` (new `no-automation` label) and deploys via `bootstrap.sh`; no manual edits to deployed `~/.claude/`. | ✅ PASS |
| **II. Parallel Agent Orchestration** | Gate cross-verification (FR-034) is delegated to the canonical `parallel_agent.py`; this feature is itself security-sensitive + architectural + >200 lines, so its own PRs require multi-agent review before merge. | ✅ PASS |
| **III. Consensus-Driven Decisions** | FR-034 reuses the exact ≥80% / 50–79% / <50% thresholds verbatim from the constitution and `command_config.yml`; gate verdicts reference them. | ✅ PASS |
| **IV. Skill-First Extensibility** | Per-phase decision logic is delivered as skill(s) in `.skillshare/skills/`; the daemon is a *separate* runner that composes existing scripts. `parallel_agent.py` and other core scripts are **not** expanded to absorb orchestrator behavior. | ✅ PASS |
| **V. Bootstrap Reproducibility** | Daemon install/config and the audit/state directory creation are idempotent and existence-guarded; the daemon exits non-zero on unrecoverable failure rather than degrading. | ✅ PASS |

**Initial gate result**: PASS — no unjustified violations. One inherent-complexity item (a long-running daemon, unusual for this on-demand-script repo) is recorded in Complexity Tracking with justification.

**Quality-gate alignment**: The spec's verification gate (FR-031) reuses the constitution's Tier 1 (blocking) / Tier 2 (advisory) gates and `APPROVED`/`NEEDS_REVIEW`/`BLOCKED` verdicts directly from `validation_criteria.yml` — the feature *operationalizes* the constitution's quality gates rather than redefining them.

## Project Structure

### Documentation (this feature)

```text
specs/004-autonomous-issue-orchestrator/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output — JSON Schemas for the envelope + per-phase payloads
│   ├── response-envelope.schema.json
│   ├── phase1-prioritization.schema.json
│   ├── phase2-clarification.schema.json
│   ├── phase3-tasking.schema.json
│   ├── phase4-analysis-gate.schema.json
│   ├── phase5-verification-gate.schema.json
│   └── phase6-pr-resolution.schema.json
├── checklists/
│   └── requirements.md  # Spec quality checklist (already created)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
configs/claude/scripts/
├── orchestrator/                 # NEW — the daemon + phase runner (Python)
│   ├── daemon.py                 # Long-running poll/dispatch loop; owns execution, time, retries
│   ├── pipeline.py               # Per-run state machine: phase order, attempt counts, pause/resume
│   ├── engine.py                 # Stateless decision-engine adapter: builds context payload,
│   │                             #   invokes the phase skill, validates the response envelope
│   ├── consensus.py              # Thin wrapper over parallel_agent.py for gate cross-verification
│   ├── audit.py                  # Append-only JSONL audit (skillclaw_audit.py pattern) + redaction hook
│   └── redact.py                 # Secret/PII masking (reuses skillclaw_scrub.py)
├── parallel_agent.py             # REUSED unchanged — cross-verification + consensus scoring
├── git_ops.sh                    # REUSED — issue/PR operations
├── git_platform.sh               # REUSED — github/gitlab/git detection
├── skillclaw_audit.py            # REUSED as the audit-log pattern reference
└── skillclaw_scrub.py            # REUSED for redaction patterns

configs/claude/config/
├── orchestrator.yml              # NEW — phase order, retry cap (2), hourly resource poll,
│                                 #   consensus threshold refs, redaction pattern set, audit path
├── command_config.yml            # REUSED — consensus thresholds, model selection, error recovery
├── validation_criteria.yml       # REUSED — Tier 1/Tier 2 criteria for the verification gate
└── labels.yml                    # MODIFIED — add the `no-automation` block label

.skillshare/skills/               # NEW phase-decision skills (Skill-First, Principle IV)
└── issue-orchestrator/           # Phase contracts + prompts (one skill, phase-keyed) OR
    └── SKILL.md                  #   per-phase skills if decomposition proves clearer in Phase 1

tests/
├── python/                       # pytest — engine determinism, envelope validation, consensus
│   │                             #   mapping, retry/pause logic, redaction, audit append
│   └── test_orchestrator_*.py
└── bats/                         # bats — daemon CLI/--help, label sync, idempotent install
    └── orchestrator_*.bats
```

**Structure Decision**: Single project, extending the existing repo layout. The daemon and its helpers live in a new `configs/claude/scripts/orchestrator/` package; decision logic is a skill under `.skillshare/skills/`; configuration is a new `orchestrator.yml` plus a `labels.yml` addition. This keeps the long-running runner cleanly separated from the on-demand scripts it composes and satisfies Principle IV by leaving `parallel_agent.py` untouched.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Long-running daemon process (this repo is otherwise on-demand scripts/skills) | The feature is inherently autonomous: it must poll for external CI/CD results and human review comments and re-invoke the engine on state changes (per spec Execution Environment + Assumptions) | A purely on-demand script cannot react to asynchronous external events (CI completion, review comments) without an outer scheduler; a cron/once-per-invocation model cannot hold the per-run pipeline state or honor the hourly resource-pause poll without effectively reimplementing a daemon |
| Per-run pipeline state persisted to disk | The decision engine is stateless by design (FR-006); attempt counts, selected issue, and current phase must live *somewhere* across invocations | Holding state in the engine violates FR-006 (statelessness) and breaks determinism/resumability; in-memory-only state is lost on the token-exhaustion pause/resume (FR-035) |
