---
name: spec-implement-loop
description: "Use once spec/plan are approved and ready to implement — critic-gated loop (CDDL): developer writes, reviewer/QA/architecture critics gate on zero findings. Never commits or pushes."
---

# Critic-Gated Implementation Loop (CDDL)

Runs a completed feature through an adversarial loop orchestrated with **native
sub-agents**. **Do not** use the parallel-review skill for personas — panel
consensus is a different workflow.

## Personas (strict separation)

| Persona | OMP role | Writes code? | Phase |
|---------|----------|--------------|-------|
| **Developer** | Omit `agent` (default implementation worker) | **Yes — only role** | 2 |
| **Developer reviewer** | `reviewer` | **Never** | 2 |
| **QA / security critic** | `security-reviewer` | **Never** | 1 + 2 |
| **Architecture critic** | `reviewer` | **Never** | 1 + 2 |

The orchestrator (you) **never** writes implementation code — only dispatches
sub-agents, runs verification, parses verdicts, persists run artifacts, and
stages on success.

**Completion:** phase 2 succeeds only when the developer reviewer, QA critic,
and architecture critic **each** return `approve` with **zero findings** on the
same iteration. Any findings → feed back to the developer and iterate.

## Sub-agent dispatch

> Sub-agents: **always** — one fresh worker per persona per round or iteration.

Use one OMP `task` call for each ready persona batch, in waves of at most 32.
Phase-1 QA and architecture critics may run together; phase-2 reviewers run
only after the developer's verification result is available. Every child gets
one bounded charter and artifact paths, executes directly, and never
redispatches. Use `hub` only to coordinate or wait. The parent parses verdicts,
gates progress, validates evidence, and aggregates the result.

If `task` is unavailable, perform the corresponding work inline and report
`DEGRADED`. Never use a provider CLI as an interactive fallback.

See `../../runtime/references/sub-agent-dispatch.md` for the shared role and
batching rules.

Charters are packaged under `../../runtime/prompts/cddl/`:

- `developer.md` — code author
- `developer-reviewer.md` — spec/plan + quality gate
- `qa-critic.md` — security / validation / runtime safety
- `arch-critic.md` — layering / design / DRY

Dispatch templates live in this skill's `prompts/` directory. Hand workers
**file paths**, not pasted artifacts. `cddl_invoke.py` remains a separate
noninteractive, headless API; it is not part of this interactive workflow.

## Prerequisites

- Feature branch (not default); clean tree unless operator passes `--allow-dirty`
- Resolvable spec (+ optional plan): speckit feature dir or superpowers design
  doc — discovery per `../../runtime/references/spec-artifact-discovery.md`
- Installed verification tools for the selected project gate

## Procedure

### 0. Pre-flight (orchestrator, inline)

1. Refuse default branch and dirty tree (unless `--allow-dirty`).
2. Resolve spec + plan; write `<RUN_DIR>/context.md` (paths, layout, verify cmd,
   iteration/round limits, clarification answers).
3. Create run dir:
   `${XDG_STATE_HOME:-$HOME/.local/state}/manifest/cddl/runs/<repo-slug>/<run-id>/`
   with `state.json` (`phase`, `iteration`, `round`, `status`).

Defaults: clarification rounds **3**, implementation iterations **10**.

### 1. Phase 1 — clarification gate (no code)

1. Dispatch **QA critic** (`security-reviewer`) and **architecture critic**
   (`reviewer`) in one OMP `task` batch with `reviewer-dispatch.md`, phase 1,
   and spec/plan artifacts.
2. Parse last `cddl-verdict` block from each output (`prompts/verdict-format.md`).
3. If **either** has `questions` findings → write `questions.md`, relay to the
   operator, collect answers → `answers-<round>.md`, append to `context.md`,
   next round.
4. If **both** `complete` with zero findings → enter phase 2.

If rounds exhaust with open questions → **gate failure** (no code produced);
write `report.md` and stop.

### 2. Phase 2 — implement → verify → triple review

For each iteration until all three reviewers approve or iterations exhaust:

1. **Developer** (default implementation worker, not a named `agent`) —
   `developer-dispatch.md`. Only this worker may modify the repo.
2. **Verification** (parent): run the verify command from context (or
   `/manifest-code-quality:project-verify`). On failure, write deficiencies to
   `iterations/<n>/verify.log`, skip critics, and send that output to the next
   developer iteration.
3. Generate review package: `git diff` + `git diff --cached` →
   `iterations/<n>/review-package.diff`.
4. Dispatch **developer reviewer** and **architecture critic** as `reviewer`,
   and **QA critic** as `security-reviewer`, in one OMP `task` batch.
5. Parse verdicts. If **any** persona has findings → merge into
   `iterations/<n>/findings.md` for the next developer dispatch.
6. If **all three** `approve` with **empty findings** → success (step 3).

If iterations exhaust without triple approval → **ceiling failure**; leave work
applied but **unstaged**; `report.md` lists per-persona outstanding findings.

### 3. Success disposition

- `git add --` only paths from the final approved iteration (never pre-existing
  dirt, never unrelated files).
- **Never** commit, push, or merge.
- Write `report.md`; tell the operator staged paths (`git diff --cached --name-only`).

## Operator relay (phase 1)

When critics ask questions, present them conversationally, collect answers in one
message, persist to `answers-<round>.md`, and continue — one continuous session.
Do not ask the operator to run CLI tools.

## Headless API boundary

`../../runtime/cddl/cddl_invoke.py` remains available to programmatic,
noninteractive callers that need one stdin-driven provider invocation. Its
`CDDL_INVOKE_PROVIDER` and `CDDL_INVOKE_CLI` controls apply only to that API;
they never replace OMP `task` in this interactive loop.

## Persistence

Per iteration: `developer-report.md`, `developer-reviewer.md`, `qa-critic.md`,
`arch-critic.md`, `verdicts.json` (parsed), `verify.log`, `findings.md`.

Keep everything under the run dir (manual prune: `rm -rf <run-id>`).

## What this skill does NOT do

- Use the cross-model parallel-review interface for personas
- Let critics or the developer reviewer write code
- Commit or push
