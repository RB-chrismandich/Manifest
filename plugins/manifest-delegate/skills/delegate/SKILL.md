---
name: delegate
description: Delegate work to local agent CLIs or Jules remote GitHub sessions; task submission, status, results, and capability-aware follow-up.
---

# Delegate

Dispatches work to a backend registered in
`plugins/manifest-delegate/config/backends.json` (currently `codex`,
`claude`, `antigravity`/`agy`, `cursor`, `devin`, `jules`) through
`scripts/delegate.py`. This skill is
the human-facing entry point; it never talks to a backend CLI directly.

## Verbs

- **Delegate a task** — `delegate.py task <prompt>` (or `--task-file FILE`,
  or `-` for stdin; `--prompt-file` remains a deprecated alias). Runs in the foreground by default
  (`--wait`); pass `--background` to get a `job_id` back immediately.
- **Follow up on a job** — `--resume JOB_ID` (or `--resume-last`) to
  continue that backend's session with new instructions; `--fresh` to
  explicitly skip resume.
- **Second opinion** — `--second-opinion --of JOB_ID --task-file FILE` (or
  `-` plus piped stdin) combines a freshly resubmitted task only with bounded,
  attempt-bound findings from the prior job.
- **Job verbs** — `status [JOB_ID|--all] [--wait [--timeout N]]`,
  `result JOB_ID`, `cancel JOB_ID`. `JOB_ID` accepts a unique prefix. `cancel`
  and timeout kill the backend's process group (best-effort: a descendant that
  calls `setsid()` to detach escapes it — the backend's own sandbox still scopes
  its writes; reliable containment of detached descendants is future hardening).
- **Transfer** — `transfer --backend NAME --source TRANSCRIPT` hands a
  session to another surface using that backend's declared transfer
  contract (`transfer` in `backends.json`; `null` means unsupported).
  `--source` is required: transfer never infers the transcript (a worktree can
  hold several sessions and none identifies the caller), so name it explicitly.
- **Review** — `review [--adversarial [FOCUS...]] [--base REF] [--scope
  auto|working-tree|branch]` reviews local git state on a backend,
  standalone (not tied to a prior `task`).

## Backend selection and scope

Pass `--backend NAME` (id or alias, e.g. `agy`); omitting it uses the
registry's configured default. Local backends default to **read-only**
(its `sandbox.read_only_args`); pass `--write` to opt into
`sandbox.write_args` for that one call. Never assume write scope — it is
per-invocation, not sticky across resumes.

Jules uses a separate remote contract. Read `references/prompting-jules.md` first.
Submit with `--backend jules --remote-write --repo OWNER/REPO --remote-base
provider-selected`. This authorizes cloud work; it cannot pin a branch or upload
local edits. Submission returns pending state and a session URL, not task success.
Use `status JOB_ID --wait --timeout 600` to observe cloud progress, `pull JOB_ID`
to fetch a completed patch, then `apply JOB_ID` after inspecting the artifact.
Remote resume, cancellation, model chains, reviews, second opinions, and review
gates are rejected. An unknown submission is never automatically retried. The
local cancellation/timeout and result-envelope rules below apply to local backends.
`status --all` is a cached overview; query a remote job ID to refresh its status.

## Before composing a delegation prompt

Load the matching `references/prompting-<backend>.md` for the resolved
backend (`prompting-codex.md`, `prompting-claude.md`,
`prompting-agy.md`, `prompting-cursor.md`, `prompting-devin.md`, `prompting-jules.md`) — each
covers that backend's cold-start assumptions,
sandbox framing, and tier conventions. Do this before writing the prompt
text; `delegate.py` itself only injects the envelope contract (FR-007,
research.md D10), not backend-specific prompting guidance.

## Second-opinion flow

`--second-opinion --of JOB_ID` re-runs a prior job's task on a different
backend for cross-verification:

- Fresh non-empty task text is mandatory through stdin (`-`) or `--task-file`;
  positional task text is rejected so the resubmission boundary is explicit.
- Prior context is limited to the source job ID and validated `title`, `detail`,
  and `severity` findings belonging to one current attempt. Prompt summaries,
  raw output/errors, prior task text, envelopes, sessions, and attempt history
  are never copied into the new prompt.
- The run is forced **read-only** regardless of `--write` — a second
  opinion never mutates the workspace.
- If `--backend` resolves to the same backend as the original job, the
  CLI warns on stderr and lists other currently-`ready` backends as
  alternatives (probed live, not just configured) before proceeding
  anyway — a same-backend rerun still runs, it just isn't independent.
- Both passes are attributed in the final output: the original backend
  (from the referenced job) and the second-opinion backend (from
  `--backend`) are each named, never merged into one unlabeled result.

## Fallback recovery

A background or JSON run in confirm mode can settle as `fallback_pending`.
Resolve it with the exact `version` and `recovery_id` printed by `status`:

```bash
printf '%s' 'freshly resubmitted task' | delegate.py task --resume JOB_ID \
  --expected-version VERSION --recovery-id RECOVERY_ID \
  --fallback-decision approve -
delegate.py task --resume JOB_ID --expected-version VERSION \
  --recovery-id RECOVERY_ID --fallback-decision reject
delegate.py cancel JOB_ID --expected-version VERSION --recovery-id RECOVERY_ID
```

Reject and cancel are task-free and end in `fallback_rejected`; repeating the
same authenticated action is idempotent. If worker ownership reached or may
have reached backend dispatch but the outcome cannot be proved, the job ends in
non-resumable `dispatch_unknown` instead of risking a duplicate submission.

## Review flow

`review` is the backend-generic replacement for baseline
`/codex:review`/`/codex:adversarial-review`:

- The dispatcher assembles the diff itself (per `--base`/`--scope`); you
  never hand it a diff.
- Always **read-only** — `review` has no `--write` flag at all, so
  findings are never auto-applied (FR-008). Relay findings and let the
  developer decide what to change.
- `--adversarial [FOCUS...]` switches to a challenge-the-design prompt;
  free-text focus words narrow what to attack (e.g. `--adversarial auth
  boundary`).
- Findings come back severity-first in the envelope — surface the
  highest severity first, same as any other envelope (see below).
- Foreground/background and job verbs (`status`, `result`, `cancel`) work
  identically to `task`.

## Reading results

`delegate.py` normalizes every backend's last fenced JSON block into a
result envelope. See `references/result-envelope.md` before relaying a
result to the user — it governs presentation (what to surface first on
failure, never fabricating a `changes` entry, and so on), not extraction.

## Model tiers

Pass `--model TIER` using a **tier name** from
`configs/claude/references/harness-routing.md`, never a raw model ID —
the registry resolves tier names to each backend's current model.

## Native host orchestration

`delegate.py` is the external-job runtime, not a native fan-out scheduler. The
current host's parent decomposes work, selects the backend and model tier,
defines input revision/diff, read/write scope, acceptance criteria, and whether
the submission is fresh or resumed. It also owns result validation and final
synthesis.

- **OMP:** after `delegate-runner` appears in the available-agent roster, submit
  independent, ready relay units through native `task` batching and coordinate
  them with `hub`. Do not put a `model` field on an OMP task item; an OMP user
  may override the runner through `task.agentModelOverrides`. OMP specialist
  work remains native.
- **Claude Code:** invoke the discovered plugin-qualified
  `manifest-delegate:delegate-runner` agent for each independent relay unit and
  collect its native background agents. Keep its `model: sonnet` plugin default
  separate from dispatcher `--model TIER`.
- **Both:** resolve the installed plugin root from the loaded skill location,
  compose one quoted absolute command such as
  `python3 "/installed/manifest-delegate/scripts/delegate.py" task --wait --json --backend codex --task-file "/session/task.txt"`
  with an explicit working directory, then give that command to the runner.
  Use stdin instead of `--task-file` when appropriate. Never assume a source
  checkout path or that `CLAUDE_PLUGIN_ROOT` exists in OMP.

Runner discovery, a usable native runner model, and backend readiness are
separate prerequisites. `delegate.py setup` proving a backend `ready` does not
prove either host can discover or run the relay agent. Report an unavailable
native capability as `DEGRADED`. For an explicitly requested external backend,
the parent may run the same dispatcher command itself sequentially and must say
native fan-out was unavailable; it must not substitute its own answer or silently
change backend.

### Lifecycle and concurrency

Native child completion, an external job's terminal state, and parent acceptance
are distinct. Use `task --wait --json` or `review --json` for a relay expected
to finish with its native child. Use `--background` only for a deliberately
detached external job: record its returned `job_id`, backend, unit, and input
scope in the parent session, then explicitly choose `status`, `result`,
`cancel`, resume, or recovery later. A vanished runner does not cancel its job;
never relaunch an uncertain dispatch without inspecting its known job.

Read-only comparison jobs may run concurrently only while their input revision
or diff remains stable. Serialize mutation in one workspace. Parallel writes
require pre-existing, separately owned workspaces/worktrees and a
parent-owned integration step; this skill does not create them. Preserve
per-invocation `--write`, always-read-only reviews and second opinions, and
Jules' separate `--remote-write`, repository, and provider-selected-base
authorization.

External task prompts must prohibit recursive delegation and tool installation.
Ordinary native children cannot orchestrate descendants; only
`delegate-runner` may perform its one parent-composed dispatcher call.

### Multi-result presentation

Collect every underlying envelope before drawing a conclusion. The parent may
add a separate **Parent aggregation** section that deduplicates verified
findings and attributes every item to its job ID and backend. It must retain
each raw relay unchanged, surface failures and follow-ups, label changed
revision/diff scopes as non-comparable, and leave disagreement unresolved where
evidence does not decide it. Text overlap and vote percentages are not
correctness; partial, malformed, absent, unavailable, or failed results never
become a clean review.
