# Phase 0 Research: Autonomous Issue Implementation Orchestrator

**Date**: 2026-06-14 | **Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

All Technical Context unknowns are resolved below. Each item reuses existing Manifest infrastructure wherever possible, per the constitution (Principle I Config-as-Code, Principle IV Skill-First).

---

## R1 — How the daemon invokes the stateless decision engine

**Decision**: The daemon (`daemon.py`) builds a JSON **context payload** for the current phase and invokes the decision engine through a single headless CLI-agent call (via the existing `parallel_agent.py` backend selection / OAuth-CLI fallback), passing the phase directive + payload and capturing the model's single JSON-envelope response. The engine's behavior is defined by a **skill** (`.skillshare/skills/issue-orchestrator/`), keyed by phase. `engine.py` is a thin adapter that constructs the payload, dispatches the call, and validates the returned envelope against the phase's JSON Schema.

**Rationale**: Reuses the proven OAuth-CLI fallback already added in PR #333 (`select_backend()`), so the orchestrator runs on OAuth-only machines without an API key. Keeping the engine as a skill honors Principle IV and keeps prompts version-controlled and per-platform deployable. Schema validation at the adapter boundary enforces FR-001/FR-002 (single, well-formed envelope) deterministically.

**Alternatives considered**: (a) Direct Anthropic SDK calls — rejected: reintroduces the SDK/API-key gap that PR #333 closed and bypasses the multi-backend story. (b) Embedding phase prompts inside `daemon.py` — rejected: violates Principle IV (Skill-First) and makes prompts harder to review/evolve.

## R2 — Determinism of an LLM-backed engine (FR-003)

**Decision**: Treat determinism as a *contract-level* guarantee enforced by (1) temperature-0 / greedy decoding for engine calls, (2) fully specifying all inputs in the context payload (no hidden state, FR-006), (3) schema-validated, canonically-ordered output fields, and (4) a golden-transcript regression test set in `tests/python/` that re-invokes recorded payloads and asserts byte-identical envelopes. Where a model cannot guarantee bitwise reproducibility, the daemon records the response in the audit log and determinism is asserted at the *structured-field* level (ordering, naming, content) rather than raw token stream.

**Rationale**: SC-002 requires identical output for identical input; FR-003 scopes this to "ordering, naming, or phrasing of structured fields." Temperature 0 + canonical serialization + payload-complete inputs is the standard, testable way to meet that without claiming impossible bitwise LLM determinism.

**Alternatives considered**: Caching responses by payload hash — kept as an optimization, not the primary guarantee, because it would mask non-determinism rather than enforce it.

## R3 — Gate cross-verification & consensus mapping (FR-034)

**Decision**: At the two gates only, `consensus.py` calls `parallel_agent.py` (unchanged) to obtain N independent agent verdicts on the gate decision, then maps the agreement ratio to the constitution's bands: **≥80% → auto-proceed**, **50–79% → proceed with disagreements highlighted as advisory**, **<50% → `needs_escalation`**. Thresholds are read from `command_config.yml` (single source of truth), not hardcoded.

**Rationale**: Principles II & III mandate `parallel_agent.py` and these exact thresholds; `command_config.yml` already defines them. This makes the orchestrator a *consumer* of the existing consensus engine rather than a fork of it (Principle IV).

**Alternatives considered**: A bespoke voting routine inside the orchestrator — rejected: duplicates `parallel_agent.py` and risks threshold drift from the constitution.

## R4 — Durable append-only audit trail (FR-029)

**Decision**: Reuse the `skillclaw_audit.py` JSONL pattern: one append-only `audit-<run>.jsonl` per pipeline run under a `chmod 700` state directory (`~/.claude/state/orchestrator/`). Each line records `{timestamp, run_id, phase, status, reasoning_trace, escalation, consensus_summary}`. Writes are fail-open for *observability* (a failed audit write logs a warning and does not crash the pipeline) but the audit path itself is created idempotently (Principle V).

**Rationale**: `skillclaw_audit.py` is the established, tested precedent in this repo (314-line JSONL logger, fail-open, `chmod 700`). Reusing its shape gives consistency and avoids inventing a second audit mechanism.

**Alternatives considered**: SQLite — rejected: adds a dependency and migration surface for what is fundamentally an append-only event log; JSONL is greppable and matches repo norms.

## R5 — Secret/PII redaction before persistence (FR-038)

**Decision**: `redact.py` wraps `skillclaw_scrub.py`'s pattern set to mask known secret/credential/PII shapes (API keys, tokens, private keys, emails) in the reasoning trace and payload **before** the audit writer persists them. Redaction runs as a mandatory hook inside `audit.py` so no durable write can bypass it. The pattern set is configurable in `orchestrator.yml` and tested against a fixture corpus of known secret shapes (SC-016).

**Rationale**: `skillclaw_scrub.py` already exists for exactly this class of scrubbing; routing every persisted write through it guarantees FR-038 at a single chokepoint rather than relying on call-site discipline.

**Alternatives considered**: `semgrep`-based secret detection — heavier and process-spawning per write; kept as an optional CI-time backstop, not the inline path.

## R6 — Resource-pause (token/credit exhaustion) detection & resume (FR-035)

**Decision**: The daemon detects token/credit exhaustion from the backend invocation result (the same Credit-Exhaustion signal `parallel_agent.py` surfaces) and classifies it as a **transient** `blocking_state`. It does not increment the FR-027 attempt counter, does not escalate, persists the current pipeline state, and schedules a re-invocation of the same phase when capacity returns or on a periodic poll (default **hourly**, configurable in `orchestrator.yml`). In-progress per-run state on disk guarantees no work is discarded.

**Rationale**: Matches the user-specified pause-and-resume behavior and the repo's documented Credit-Exhaustion handling (`references/parallel-agent.md`). Separating *transient resource* failures from *input* failures (FR-005) prevents false escalations and wasted attempts.

**Alternatives considered**: Immediate escalation on exhaustion — rejected: spams humans for a self-healing condition. Tight retry loop — rejected: burns no-op cycles and risks rate-limit amplification; hourly poll is the conservative default.

## R7 — Platform-agnostic issue/PR operations

**Decision**: All issue read, label read/write, branch, and PR-open/comment operations go through `git_ops.sh` (with `git_platform.sh` detecting github/gitlab/git). The engine never calls these directly — it emits *decisions*; the daemon executes them via these wrappers.

**Rationale**: `git_ops.sh` is already the platform-agnostic wrapper in this repo, preserving the gh/glab abstraction (spec Assumptions) and keeping the engine free of side effects (FR-006).

**Alternatives considered**: Direct `gh`/`glab` calls from the daemon — rejected: re-implements detection and branching logic that `git_ops.sh` already encapsulates.

## R8 — `no-automation` kill-switch label provisioning (FR-037)

**Decision**: Add `no-automation` to `configs/claude/config/labels.yml` and provision it across platforms via the existing `label_sync.sh`. The daemon reads the active issue's labels through `git_ops.sh` and re-checks for `no-automation` before each phase advance; presence halts the issue (reported as held).

**Rationale**: `labels.yml` + `label_sync.sh` is the canonical, already-built label registry/sync mechanism (Principle I). No new label tooling is needed.

**Alternatives considered**: A separate config list of blocked issue IDs — rejected: labels are the native, human-visible control surface on the issue tracker and require no extra store.

## R9 — Per-run pipeline state & resumability

**Decision**: `pipeline.py` persists a small JSON state file per run (`run_id`, `selected_issue`, `current_phase`, `attempt_counts`, `last_status`, `paused`) alongside the audit log. The stateless engine is always re-driven from this state + freshly fetched external inputs, never from memory.

**Rationale**: Reconciles FR-006 (stateless engine) with FR-027 (attempt cap) and FR-035 (pause/resume) — the state the engine is forbidden to hold lives in the daemon's per-run file, keeping the engine pure and the pipeline resumable.

**Alternatives considered**: Reconstructing state by replaying the audit log — rejected: more fragile and slower than an explicit compact state file; the audit log remains the immutable history, the state file the working cursor.

---

## Resolved unknowns summary

| Technical Context item | Resolution |
|------------------------|-----------|
| Engine invocation mechanism | Headless CLI-agent call via `parallel_agent.py` backend; logic in a skill (R1) |
| Determinism strategy | Temp-0 + payload-complete inputs + schema canonicalization + golden tests (R2) |
| Consensus integration | `parallel_agent.py` at gates, thresholds from `command_config.yml` (R3) |
| Audit storage | JSONL append-only, `chmod 700`, `skillclaw_audit.py` pattern (R4) |
| Redaction | `skillclaw_scrub.py` as mandatory pre-write hook (R5) |
| Resource pause/resume | Transient `blocking_state`, hourly resume poll, no attempt increment (R6) |
| Issue/PR ops | `git_ops.sh` + `git_platform.sh` (R7) |
| Kill-switch label | `labels.yml` + `label_sync.sh` (R8) |
| Pipeline state | Compact per-run JSON state file (R9) |

**No `NEEDS CLARIFICATION` items remain.** Ready for Phase 1 design.
