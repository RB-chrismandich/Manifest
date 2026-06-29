# Contract: `lifecycle.sh` CLI + decision core

**Feature**: 365-lifecycle-codification | Per research.md D1/D2. Bash + embedded `python3 -c`, mirroring `merge_decision.sh`/`verification_gate.sh`.

`configs/claude/scripts/lifecycle.sh` — the shared state-machine. The `/lifecycle` skill and the autodev loop both call it. Every entry point handles `--help` (≤15 lines, exit 0, before any state/dependency lookup) and routes errors through `err()` (repo Script Conventions).

## Subcommands

| Subcommand | Purpose | Exit codes |
|---|---|---|
| `init <entry-point>` | Parse provider/entity/tier, create the Track, set `current_phase=specify` | 0 created · 1 I/O · 2 unrecognized entry point (no track) |
| `status [<track-id>] [--json]` | Report current phase, completed phases, outstanding gates (FR-007) | 0 · 2 no such track |
| `decide <signals-json>` | **Pure core.** Map signals → action. **Always exits 0**, fails **closed** (malformed → refuse) | always 0 |
| `advance <track-id>` | Run the current phase's exit check; on `allow` persist next phase, else refuse/warn | 0 advanced · 1 refused (agent) · 3 warned (human, override available) |
| `anchor <track-id>` | Re-emit the active phase (drift re-anchoring, FR-006) | 0 |
| `regress <track-id> --to <phase> --reason <text>` | Logged backward transition (FR-005) | 0 · 2 missing reason |

`gate` is an alias spelling for the `decide`+exit-code mapping used by callers that want a non-zero exit (the loop). `decide` itself never exits non-zero so it stays unit-testable.

## `decide` I/O (the testable seam)

**Input** (`signals-json`):
```json
{
  "actor_mode": "agent|human",
  "current_phase": "implement",
  "requested_phase": "verify",
  "phase_gate": {
    "gate_type": "verdict|coverage|runner|artifact",
    "verdict": "APPROVED|NEEDS_REVIEW|BLOCKED|null",
    "exit_code": 0,
    "coverage": "OK|MISSING|null"
  },
  "completed_phases": ["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech"]
}
```

**Output**:
```json
{ "action": "allow|warn|refuse", "missing_prereq": "plan|null", "reason": "human-readable" }
```

**Decision rules** (deterministic; the bats-tested contract):
1. **Skip detection** — if `requested_phase.order > current_phase.order + 1`, or any phase with lower order ∉ `completed_phases` → `missing_prereq` = first gap. For `actor_mode=agent` → `refuse`; for `human` → `warn`.
2. **Gate evaluation** of the phase being *completed*:
   - `gate_type=verdict`: `APPROVED`→allow · `NEEDS_REVIEW`→warn · `BLOCKED`→refuse(agent)/warn(human).
   - `gate_type=runner` (verify): `exit_code 0`→allow · `1`→refuse(agent)/warn(human) · `2` (EMPTY)→refuse(agent)/warn(human) (missing coverage ≠ pass, FR-010).
   - `gate_type=coverage` (implement-exit): `OK`→allow · `MISSING`→refuse(agent)/warn(human).
   - `gate_type=artifact`: present→allow, absent→refuse(agent)/warn(human).
3. **Fail-closed**: unparseable input, unknown phase, or missing required field → `refuse` with reason `malformed-signals` (safety default, mirrors `merge_decision.sh`).

**Invariant**: identical `signals-json` always yields identical output (FR deterministic; matches the repo's pure-decide-core convention). No network, no clock, no filesystem in `decide`.

## State persistence (subcommands other than `decide`)

- **`track-id` (single definition)** ≡ `<provider>__<sanitized-entity-id>` (e.g. `jira__PROJ-123`, `github__org_repo-42`). Derived once from the entry point; used as both the in-state `track_id` and the state filename. plan.md, data-model.md, and tasks.md all reference this definition.
- Dir: `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/lifecycle/state/`, `0700`; files `<track-id>.json`, `0600`, atomic write (temp + `mv`).
- Secrets (tokens) never written; sourced from env at run time, redacted from any logged output (FR-025), reusing the smoke `StateManager` redaction approach.
- Injectable seams for tests (mirroring `pr_merge_loop.sh`): `LIFECYCLE_STATE_DIR`, `LIFECYCLE_SMOKE_CMD`, `LIFECYCLE_SPEC_REVIEW_CMD`, `LIFECYCLE_GIT_OPS_CMD`.

## Caller integration

- **`/lifecycle` skill** (`actor_mode=human` default): maps `current_phase`→the phase command(s), runs them, collects the gate signal, calls `advance`. On `warn`, surfaces the warning and allows a logged override.
- **Autodev loop** (`actor_mode=agent`): calls `gate`/`advance`; a `refuse` (exit 1) halts the unit and flags `needs-human` (FR-024); never merges past a failing gate (SC-011).
