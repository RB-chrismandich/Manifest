# Data Model: Multi-Agent Delegation Plugin

**Feature**: `675-multi-agent-delegation` | **Date**: 2026-08-05

Entities from spec.md Key Entities, refined by research.md decisions. Machine
contracts for the starred entities live in `contracts/`.

## Backend Registry Entry ★ (`contracts/backend-registry.schema.json`)

One entry per backend in `plugins/manifest-delegate/config/backends.json`
(FR-016; JSON so the stdlib-only dispatcher parses it unconditionally).
Shipped entries: `codex`, `claude`, `antigravity`.

| Field | Type | Notes |
|---|---|---|
| `id` | string, unique | Canonical key (`codex`, `claude`, `antigravity`) |
| `aliases` | string[] | e.g. `agy` → `antigravity`; unknown names are rejected with the known-backend list (edge case: never guessed) |
| `display_name` | string | For reports/attribution |
| `binary` | string | Executable probed on PATH |
| `invoke` | argv template | One-shot non-interactive execution; placeholders `{model}`, `{prompt}`, `{output_file}` |
| `resume` | argv template or `null` | `null` ⇒ backend cannot resume: dispatcher discloses and re-sends context (FR-015) |
| `model_args` | argv template | Dropped atomically when tier resolves to `auto` (cli_agents precedent) |
| `tier_source` | string | Key into `parallel_agent.yml` `model_tiers` when deployed config present; verbatim passthrough otherwise |
| `default_tier` | string | Economical default (FR-009): codex `auto`, claude `sonnet`, antigravity `flash` |
| `session_id_capture` | enum `json_field`/`jsonl_event`/`output_scan`/`none` + field/event/pattern | How to extract the resume id from run output; codex uses `jsonl_event` on the version-gated `thread.started` event of `codex exec --json` (absent on older CLIs ⇒ `session_ref` null, disclosed — never an error) |
| `input` | object | `transport` (`stdin`/`temp_file`/`argv`) + `max_payload_bytes` (transport cap) + `max_context_bytes` (model-context bound, nullable) — large prompts go via stdin or a 0600 temp file in the job dir, never argv |
| `readiness` | object | `version_cmd`, `auth_probe_cmd` (non-interactive, ≤10s timeout), `install_fix`, `login_fix` (exact remediation strings, FR-003), optional `retired_check` (detector for present-but-superseded CLIs; null on all shipped entries) |
| `sandbox` | object | `read_only_args`, `write_args` — per-backend security profile (D8: codex `--sandbox read-only|workspace-write`; claude sandbox-enabled `--settings` + read-only `--permission-mode plan`/write `acceptEdits` + tool constraints; agy `--sandbox --mode plan|accept-edits` — sandbox + explicit mode in BOTH modes); dangerous-bypass flags unrepresentable (FR-008) |
| `prompting_ref` | path | Per-backend guidance file under `skills/delegate/references/` (FR-007) |
| `services_key` | string | `services.yml` toggle honored (workspace disable outranks user enable, FR-013) |

**Validation**: unique `id`s and aliases; templates must not contain shell
metacharacters (argv arrays, never shell strings); `sandbox` flag sets drawn
from a fixed allowlist per backend. Every argv token is screened for
dangerous tokens (`dangerously|bypass`) at schema level AND re-validated by
the dispatcher at registry load — a violating registry refuses to run
(exit 2), closing the hand-edited-registry hole (D8).

## User Configuration ★ (`contracts/delegation-config.schema.json`)

`~/.claude/config/delegation.{json,yml}` (resolution: explicit >
`$MANIFEST_CONFIG_DIR` > `~/.claude/config/`; JSON parses everywhere, YAML
when PyYAML importable, `.json` wins if both exist). `setup` writes
`delegation.json` (canonical); YAML is written only when updating an
existing `.yml` with PyYAML importable (research.md D3 migration rule).
Absent ⇒ factory
defaults. Invalid or unreadable ⇒ stderr report + factory defaults (FR-013 —
deliberate divergence from `ConfigError`-raising agents config; research.md
D3).

| Field | Type | Factory default |
|---|---|---|
| `default_backend` | registry id | `codex` |
| `review_gate.enabled` | bool | `false` |
| `review_gate.backend` | registry id or null | null ⇒ `default_backend` |
| `review_gate.budget_seconds` | int 1–840 (capped; cap reported) | `600` |
| `backends.<id>.enabled` | bool | `true` (all three) |
| `backends.<id>.model` | tier name / verbatim / null | null ⇒ registry `default_tier` |
| `backends.<id>.budget_seconds` | int > 0 | `600` |

**Precedence** (readiness + delegation both enforce and attribute):
workspace `services.yml enabled: false` → `disabled (workspace)` ▸ user
`backends.<id>.enabled: false` → `disabled (user)` ▸ else enabled.
Per-invocation `--budget` > `backends.<id>.budget_seconds` > 600 (FR-012).

## Delegation Request

Transient (CLI args → one job). Fields: `task_text` (required unless resuming),
`backend` (explicit id/alias, else `default_backend`; unknown ⇒ error listing
registry), `kind` (`task` | `second-opinion` | `review` | `gate`), `mode`
(`foreground` | `background`), `write` (bool, default false — D8), `model`
(tier override), `budget_seconds` (override), `resume_target` (job id or
`--last`), `context` (free text; second-opinion carries the first pass's task
context + attributed prior findings).

**Validation**: second-opinion with same backend as the first pass ⇒ warning +
list of other ready backends (US3-AS2); context is validated against BOTH
registry bounds — `input.max_payload_bytes` (transport) and
`input.max_context_bytes` (model context) — and exceeding either ⇒ explicit
error naming the specific limit exceeded, never silent truncation (edge
case). Prompt delivery follows `input.transport`: stdin payload or a 0600
temp file in the job dir; never argv for large prompts.

## Delegation Job (record) — persistence of a request

Directory `~/.claude/.agent_outputs/delegations/<ws-slug>-<hash>/<job-id>/`
(D2): `record.json` + `output.txt` + `job.log`. Keep-last-50 per workspace.

`record.json` fields: `job_id` (short unique, prefix-matchable), `kind`,
`backend`, `model_resolved`, `status`, `pgid` (backend process group),
`worker_pid` (supervising worker — the detached plugin process that owns
timeout enforcement and the terminal write), `session_ref` (backend
thread/session/conversation id for resume; null if not captured),
`budget_seconds`, `write` (bool), `created_at` / `started_at` / `ended_at`,
`workspace_root`, `claude_session_id` (when launched from a hooked session),
`error` (actionable message on failure — never empty when failed, SC-004),
`result` (Delegation Result envelope, on completion).

**State transitions**:

```
queued → running → completed
                 → failed      (nonzero exit / malformed output / backend gap)
                 → timeout     (budget exceeded; worker killed the pgid; partial state noted)
queued|running → cancelled     (user cancel; pgid killed; CAS write — applies only while non-terminal)
```

Terminal states are immutable. **Write discipline**: every `record.json`
mutation is a compare-and-replace serialized through a per-job exclusive
lock (`fcntl.flock` on `<job-dir>/.lock`) — acquire the lock, re-read the
current record, refuse if it is already terminal, write via temp file +
atomic rename, release. The state check and the terminal write share one
critical section (a bare re-read + rename would leave a TOCTOU window in
which completion and cancel both observe non-terminal state and overwrite
each other). The worker is the
sole writer of completion terminal states; the cancel path is the only other
terminal writer, and the race between them resolves to whichever terminal
write lands first (the loser detects the terminal state under the lock and
becomes a reported no-op). `status` liveness is verified against
`worker_pid` and `pgid` on read; a dead worker with non-terminal status
triggers the **reaper**: the reader kills the recorded backend `pgid` (a
dead supervisor must not leave its backend running — FR-012), then reports
`failed` with "process died without result". The SessionEnd hook runs the
same reap over all non-terminal jobs.

**Concurrency**: multiple jobs may run per workspace (spec edge case); each
writes only its own directory — no shared index. (Baseline's
one-active-task-per-workspace limit is intentionally not inherited.)

## Delegation Result ★ (`contracts/result-envelope.schema.json`)

Normalized envelope (FR-002), identical across backends: `backend` +
`model` (attribution), `outcome` (`success` | `partial` | `failure`),
`attempted` (what was tried), `changes` (files touched or `[]`),
`succeeded` / `failed` signal lists, `follow_ups` (recommended next steps,
including the resume command when `session_ref` exists), `raw_output_path`.
Empty/malformed backend output ⇒ `outcome: failure` with "backend returned
nothing usable" (edge case) — a summary is never fabricated.

## Readiness Report

Per backend (FR-003/FR-004): `backend`, `state` ∈ `ready` | `not_installed` |
`not_authenticated` | `disabled_workspace` | `disabled_user` | `retired` |
`error`, `version` (when installed), `identity` (account/login reported by
the auth probe when its output carries one; null otherwise — satisfies
US2-AS1 "versions/identities"), `remediation` (exact fix from registry:
install cmd / login cmd / which config layer to flip — names the blocking
layer per FR-013), `probe_seconds`. Probes run in parallel; report completes
< 30s (SC-003). `retired` covers present-but-superseded CLIs (edge case) via
a registry `readiness.retired_check`/probe-failure classification.

## Review Gate Configuration

Gate config lives in User Configuration (`review_gate.*`). **At-most-once**
is enforced by the harness re-entry indicator: the Stop payload's
`stop_hook_active: true` (set when the session is already continuing from a
prior Stop-hook block) ⇒ immediate allow before any other work (D9). Each
gate run still records a `gate`-kind job (`claude_session_id` + timestamps)
as the audit trail. Edit detection follows the deterministic
finishing-turn/tool-name algorithm in contracts/delegate-cli.md. The block
reason must forbid tool use and require asking the developer ("developer
decides"). Gate failures (backend unready, timeout, malformed) fail
open with a stderr note (FR-006/US4-AS3). Gate jobs are always read-only and
never mutate files.

## Relationships

```
BackendRegistryEntry 1 ←— n DelegationRequest —→ 1 DelegationJob —→ 0..1 DelegationResult
UserConfiguration —(defaults/enables/budgets)→ DelegationRequest
UserConfiguration.review_gate —→ gate-kind DelegationJob (audit trail)
ReadinessReport —(one row per)→ BackendRegistryEntry
DelegationJob.session_ref —(resume / follow-up)→ new DelegationRequest
```
