---
name: delegate
description: Delegate a task to another agent CLI (Codex, Claude, Antigravity) for a second opinion or follow-up; background, status, cancel, resume.
---

# Delegate

Dispatches work to a backend registered in
`plugins/manifest-delegate/config/backends.json` (currently `codex`,
`claude`, `antigravity`/`agy`) through `scripts/delegate.py`. This skill is
the human-facing entry point; it never talks to a backend CLI directly.

## Verbs

- **Delegate a task** — `delegate.py task <prompt>` (or `--prompt-file
  FILE`, or `-` for stdin). Runs in the foreground by default
  (`--wait`); pass `--background` to get a `job_id` back immediately.
- **Follow up on a job** — `--resume JOB_ID` (or `--resume-last`) to
  continue that backend's session with new instructions; `--fresh` to
  explicitly skip resume.
- **Second opinion** — `--second-opinion --of JOB_ID` asks a backend to
  critique a prior job's envelope rather than redo the task.
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
registry's configured default. Every backend defaults to **read-only**
(its `sandbox.read_only_args`); pass `--write` to opt into
`sandbox.write_args` for that one call. Never assume write scope — it is
per-invocation, not sticky across resumes.

## Before composing a delegation prompt

Load the matching `references/prompting-<backend>.md` for the resolved
backend (`prompting-codex.md`, `prompting-claude.md`,
`prompting-agy.md`) — each covers that backend's cold-start assumptions,
sandbox framing, and tier conventions. Do this before writing the prompt
text; `delegate.py` itself only injects the envelope contract (FR-007,
research.md D10), not backend-specific prompting guidance.

## Second-opinion flow

`--second-opinion --of JOB_ID` re-runs a prior job's task on a different
backend for cross-verification:

- The referenced job's `prompt_summary` and `envelope` (prior findings)
  are injected into the new prompt, prefixed with attribution (`Second
  opinion requested on job <id> (backend=<name>)`), so the second backend
  sees the original task and what the first backend already found.
- The run is forced **read-only** regardless of `--write` — a second
  opinion never mutates the workspace.
- If `--backend` resolves to the same backend as the original job, the
  CLI warns on stderr and lists other currently-`ready` backends as
  alternatives (probed live, not just configured) before proceeding
  anyway — a same-backend rerun still runs, it just isn't independent.
- Both passes are attributed in the final output: the original backend
  (from the referenced job) and the second-opinion backend (from
  `--backend`) are each named, never merged into one unlabeled result.

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
