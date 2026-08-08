# Contract: `delegate.py` dispatcher CLI

Single entry point `plugins/manifest-delegate/scripts/delegate.py` — every
skill, agent, and hook shells to it; nothing else implements delegation logic.
Self-contained (stdlib-only, Python ≥ 3.9 — an early version probe exits 2
with exact remediation on older interpreters, research.md D11); degrades to
compiled factory defaults when
deployed workspace config is absent (SC-005). Config parsing under the
stdlib-only rule: plugin registry is JSON; user config `delegation.json`
always parses, `delegation.yml` honored when PyYAML is importable (else
reported + factory defaults per FR-013); `services.yml` enable flags are
extracted with a fixed-format reader matched to the generator-owned layout so
workspace disables always win; `model_tiers` is consulted only when PyYAML is
importable, else tier names pass through verbatim.

Global rules:

- `--help` on every subcommand and bare invocation: usage + flags, ≤15 lines,
  exit 0, before any config/state lookup (repo `--help` gate).
- `--json` on every subcommand: machine output; default is human-readable.
- Errors: exit non-zero with one actionable stderr line naming cause + fix
  (SC-004; never log-and-drop). Unknown backend ⇒ exit 2 + known-backend list.
- All child processes spawned as argv arrays (never shell strings), in their
  own process group. `stdin=DEVNULL` except when the registry entry's
  `input.transport` is `stdin`, where stdin carries exactly the prompt
  payload then EOF. Prompts never ride argv beyond the registry's
  `input.max_payload_bytes` — large prompts travel via stdin or a 0600 temp
  file inside the job dir (substituted at `{prompt_file}`), keeping payloads
  out of `ps`/ARG_MAX. Context exceeding `input.max_payload_bytes` or
  `input.max_context_bytes` is rejected with an error naming the specific
  limit — never truncated.
- Internal worker mode (hidden subcommand, excluded from `--help` text):
  `--background` spawns it detached (own session); the worker supervises the
  backend's process group — owns the budget timeout and process-group kill,
  writes the final envelope atomically (temp file + rename), and sets the
  terminal state exactly once. All `record.json` mutations are
  compare-and-replace serialized through a per-job exclusive lock
  (`fcntl.flock` on `<job-dir>/.lock`) — state re-read and terminal write in
  one critical section, so a terminal state, once written, is never
  overwritten (no re-read/rename TOCTOU window).

## Subcommands

### `task` — delegate (US1), second opinion (US3), follow-up (FR-015)

```
delegate.py task [--backend <id|alias>] [--background|--wait]
                 [--write] [--model <tier>] [--budget <seconds>]
                 [--resume <job-id>|--resume-last|--fresh]
                 [--second-opinion --of <job-id>]
                 [--json] [PROMPT | --prompt-file F | - (stdin)]
```

- Backend default: user config `default_backend` (factory `codex`); the chosen
  backend is always stated in output (US1-AS4).
- `--write` opts into the backend's sandboxed write mode; absent ⇒ read-only
  args (FR-008). `--second-opinion` forces read-only, injects the referenced
  job's task context + attributed findings, and warns if the target backend
  equals the original's (US3-AS2).
- Resume: replays the stored `session_ref` through the registry's `resume`
  template; backend with `resume: null` ⇒ stated plainly + context re-sent
  fresh (FR-015). `--fresh` skips the resume path.
- Foreground: blocks up to budget, prints the result envelope. Background:
  prints `job_id` + "check: delegate.py status <job_id>" and returns
  immediately (FR-014); the detached worker supervises the run to a terminal
  state even though the launcher has exited.
- Timeout: the worker kills the backend process group, marks `timeout`,
  reports partial state (FR-012).
- Exit: 0 job accepted/completed; 1 backend failure; 2 usage/unknown backend;
  3 backend unavailable (message = cause + remediation + ready alternatives,
  FR-004 — never silent fallback).

### `review` — standalone code review, incl. adversarial (FR-011/SC-002 parity)

```
delegate.py review [--backend <id|alias>] [--adversarial [FOCUS...]]
                   [--base <ref>] [--scope auto|working-tree|branch]
                   [--background|--wait] [--model <tier>] [--budget <seconds>]
                   [--json]
```

Backend-generic replacement for baseline `/codex:review` and
`/codex:adversarial-review`: reviews local git state (diff assembled by the
dispatcher per `--base`/`--scope`) on the chosen backend, foreground or
background (same job records as `task`). `--adversarial` switches to the
challenge-the-design prompt and accepts free-text focus. Always read-only
(kind=`review` forces the registry's read-only args); findings are presented
severity-first in the normalized envelope and are never auto-applied
(FR-008). Exit codes as `task`.

### `status` — job list / detail (FR-014)

```
delegate.py status [job-id-or-prefix] [--all] [--wait [--timeout <s>]] [--json]
```

No id: table of this workspace's jobs (id, kind, backend, status, elapsed,
summary). With id: full record. `--wait`: poll until terminal or timeout.
Dead-process detection: non-terminal status with a dead worker (or dead
pgid) reported as `failed` "process died without result" — and before
marking it, the reader reaps: a recorded live backend `pgid` under a dead
worker is killed (FR-012 no-orphan rule; SessionEnd performs the same sweep
for every non-terminal job).

### `result` — stored outcome (FR-014)

```
delegate.py result [job-id-or-prefix] [--json]
```

Prints the normalized envelope + `raw_output_path`. Active job ⇒ exit 1 with
"still running; delegate.py status <id> --wait". Ambiguous prefix ⇒ exit 2
listing matches.

### `cancel` (FR-014)

```
delegate.py cancel [job-id-or-prefix] [--json]
```

Resolves the active job (sole active job auto-selected; ambiguity ⇒ exit 2).
Applies only to non-terminal jobs: kills the backend process group, then
compare-and-replace-marks the record `cancelled` — the write aborts if a
terminal state landed first (completion and cancel cannot race; first
terminal write wins). Already-terminal job ⇒ no-op: the existing terminal
state is reported, the record is untouched, exit 0. Reports whether the
process was still alive.

### `setup` — readiness (US2) + gate toggle (US4)

```
delegate.py setup [--backend <id>] [--enable-review-gate [--gate-backend <id>]]
                  [--disable-review-gate] [--json]
```

Default: parallel readiness probes for every registry backend, < 30s total
(SC-003); per-backend row = state, version, exact remediation, blocking config
layer (FR-003, FR-013 attribution). Never blocks on interactive input
(US2-AS3). Gate flags write `review_gate.*` to the user config — canonical
write target `delegation.json` (created with factory defaults + the change
when no config exists). An existing `delegation.yml` is updated in place
only when PyYAML is importable (YAML is never written otherwise); a `.yml`
present without PyYAML is reported unreadable, and `delegation.json` is
written and takes precedence (research.md D3 migration rule). The new state
is confirmed.

### `transfer` — session handover (FR-015)

```
delegate.py transfer [--backend <id>] [--source <transcript.jsonl>] [--json]
```

codex: performs the app-server external-session import via a short-lived
direct `codex app-server` invocation; prints the thread id + resume command.
Backends without import support: states so and offers `task` with re-sent
context. Source path defaults to the SessionStart-captured transcript path;
it must canonicalize (realpath, symlinks resolved) to a path under
`~/.claude/projects/` or `~/.claude/transcripts/` — the two transcript roots
the harness uses (path-traversal guard, widened from the baseline's
projects-only rule).

The default only applies when **exactly one** captured session matches the
current workspace. Nothing in a `transfer` invocation identifies the calling
session, so when two sessions are open in the same worktree the command exits
non-zero, names the candidate session ids, and requires `--source` (or
`MANIFEST_TRANSCRIPT_PATH`). Guessing — "the most recent cwd match" — could
hand the caller the other session's entire transcript. SessionEnd evicts the
finishing session's capture entry, which is what returns the surviving session
to the no-`--source` path.

### `gate` — soft review gate engine (US4; called by the Stop hook)

```
delegate.py gate --transcript <path> [--stop-hook-active] [--json]
```

**Stop payload (stdin JSON to the hook wrapper)**: `session_id`,
`transcript_path`, `cwd`, `hook_event_name: "Stop"`, `stop_hook_active`
(bool). The wrapper forwards `transcript_path` and, when true,
`--stop-hook-active`.

**At-most-once**: `--stop-hook-active` is the harness re-entry indicator
(this Stop fires while the session is already continuing from a prior
Stop-hook block) ⇒ immediate `allow`, before any other work. A `gate`-kind
job is still recorded per run as the audit trail.

**Edit detection (deterministic)**: scan the transcript JSONL for the last
user message that is not a tool-result carrier; the finishing turn = all
entries after it; code edits are present iff any assistant `tool_use` in
that window names `Edit`, `Write`, `MultiEdit`, or `NotebookEdit`. Bash is
deliberately not classified (best-effort under-trigger; the gate is
fail-open).

Check order: gate disabled / `--stop-hook-active` / no code edits in the
finishing turn / backend unready ⇒ `allow` (exit 0). Otherwise runs one
read-only review delegation (gate budget) and emits
`{"decision":"block","reason":<text>}` on
stdout exactly once. The reason text MUST present findings severity-first,
instruct the session to make no tool calls and no edits in response, and
require it to relay the findings and ask the developer how to proceed —
ending "developer decides". Every failure mode fails **open**, emitting
hook-JSON `{"systemMessage": "review gate skipped: <cause>"}` — the
harness's defined developer-visible channel — plus a stderr note (FR-006;
US4-AS3's "reports the gap" is satisfied by the systemMessage, not by
stderr alone). Never edits files.

### `resume-candidate` — follow-up detection (baseline parity)

```
delegate.py resume-candidate [--backend <id>] --json
```

Reports `{available, job_id, backend, session_ref, age}` for the newest
resumable job, so the `delegate` skill can offer continue-vs-fresh.

## Readiness/report output (human form)

```
backend      state              version   fix
codex        ready              1.x       —
claude       not_authenticated  2.x       run: claude  (then /login)
antigravity  disabled_workspace 1.1.8     enable in ~/.claude/config/services.yml (workspace layer outranks user enable)
```

`--json` rows additionally carry `identity` (account/login from the auth
probe, when reported) — US2-AS1.
