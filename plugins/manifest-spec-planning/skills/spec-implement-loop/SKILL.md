---
name: spec-implement-loop
description: "Use once spec/plan are approved and ready to implement — critic-gated loop (CDDL): developer writes, reviewer/QA/architecture critics gate on zero findings. Supports --assurance standard|high-assurance. Never commits or pushes."
---

# Critic-Gated Implementation Loop (CDDL)

Runs a completed feature through an adversarial loop orchestrated with **native
sub-agents**. **Do not** use the parallel-review skill for personas — panel
consensus is a different workflow.

## Assurance modes

Select with `--assurance standard|high-assurance`; default `standard`. Reject
any other value before touching the run dir.

- **standard** — the orchestrator performs clarification inline against the
  spec and plan, escalating to the operator only unresolved *material*
  questions (ones whose answer would change what gets built). No QA or
  architecture clarification sub-agents. Phase 2 dispatches the developer and
  **one** independent developer reviewer.
- **high-assurance** — independent QA and architecture clarification
  sub-agents run phase 1. Phase 2 dispatches all three critics (developer
  reviewer, QA critic, architecture critic).

Both modes preserve: verification before any review dispatch, persona
ownership (only the developer writes code), the iteration/round ceilings, and
the scoped [success disposition](#3-success-disposition).

**Persistence and resume.** The selected mode is written to `state.json` as
`assurance` and to `context.md` before phase 1 starts. Resuming a run reads
`state.json.assurance` and uses it; an operator-supplied `--assurance` that
disagrees with the recorded value is a **pre-flight failure** — report the
conflict and stop before dispatching anything. A run whose `state.json`
predates this field (no recorded `assurance`) must not be silently defaulted
to `standard`: inspect its persisted `iterations/*/` artifacts — three critic
reports per iteration (`developer-reviewer.md`, `qa-critic.md`,
`arch-critic.md`) means the run was operating as `high-assurance`; a lone
`developer-reviewer.md` per iteration means `standard`. Record that
classification in `state.json` before continuing; never reinterpret a run
with a visible three-persona history as `standard`.

## Personas (strict separation)

| Persona | OMP role | Writes code? | Standard | High assurance |
|---------|----------|--------------|----------|----------------|
| **Developer** | Omit `agent` (default implementation worker) | **Yes — only role** | Phase 2 | Phase 2 |
| **Developer reviewer** | `reviewer` | **Never** | Phase 2 | Phase 2 |
| **QA / security critic** | `security-reviewer` | **Never** | — | Phase 1 + 2 |
| **Architecture critic** | `reviewer` | **Never** | — | Phase 1 + 2 |

The orchestrator (you) **never** writes implementation code — only dispatches
sub-agents, runs verification, parses verdicts, persists run artifacts, and
stages on success.

**Completion (standard):** phase 2 succeeds when the developer reviewer
returns `approve` with zero findings on the current iteration.
**Completion (high-assurance):** phase 2 succeeds only when the developer
reviewer, QA critic, and architecture critic **each** return `approve` with
**zero findings** on the same iteration. Any findings → feed back to the
developer and iterate.

## Sub-agent dispatch

> Sub-agents: **always** — one fresh worker per persona per round or iteration.

Follow the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
In high-assurance mode, phase-1 QA and architecture critics may run together;
phase-2 reviewers run only after the developer's verification result is
available. Standard mode has one reviewer; high-assurance has three. Every
child receives one bounded charter and artifact paths. The parent parses
verdicts, gates progress, and validates evidence.

Charters are packaged under `../../runtime/prompts/cddl/`:

- `developer.md` — code author (both modes)
- `developer-reviewer.md` — spec/plan + quality gate (both modes)
- `qa-critic.md` — security / validation / runtime safety (high-assurance only)
- `arch-critic.md` — layering / design / DRY (high-assurance only)

Dispatch templates live in this skill's `prompts/` directory. Hand workers
**file paths**, not pasted artifacts. `cddl_invoke.py` remains a separate
noninteractive, headless API; it is not part of this interactive workflow.

## Prerequisites

- Feature branch (not default); clean tree unless operator passes `--allow-dirty`
- Resolvable spec (+ optional plan): structured feature dir (`specs/`) or a design doc —
  discovery per `../../runtime/references/spec-artifact-discovery.md`
- Installed verification tools for the selected project gate

## Procedure

### 0. Pre-flight (orchestrator, inline)

1. Refuse default branch and dirty tree (unless `--allow-dirty`).
2. Resolve the assurance mode per [Assurance modes](#assurance-modes); on
   resume, reconcile with the recorded mode and fail before dispatching
   anything on conflict.
3. Resolve spec + plan; write `<RUN_DIR>/context.md` (paths, layout, verify
   cmd, iteration/round limits, assurance mode, clarification answers).
4. Create run dir:
   `${XDG_STATE_HOME:-$HOME/.local/state}/manifest/cddl/runs/<repo-slug>/<run-id>/`
   with `state.json` (`phase`, `iteration`, `round`, `status`, `assurance`).

Defaults: clarification rounds **3**, implementation iterations **10**.

### 1. Phase 1 — clarification gate (no code)

**High-assurance:**

1. Dispatch **QA critic** (`security-reviewer`) and **architecture critic**
   (`reviewer`) in one OMP `task` batch with `reviewer-dispatch.md`, phase 1,
   and spec/plan artifacts.
2. Parse last `cddl-verdict` block from each output (`prompts/verdict-format.md`).
3. If **either** has `questions` findings → write `questions.md`, relay to the
   operator, collect answers → `answers-<round>.md`, append to `context.md`,
   next round.
4. If **both** `complete` with zero findings → enter phase 2.

**Standard:**

1. The orchestrator reviews the spec and plan directly against the acceptance
   criteria and identifies unresolved *material* questions — ones whose
   answer would change what gets built. No sub-agent dispatch.
2. If any exist → write `questions.md`, relay to the operator, collect
   answers → `answers-<round>.md`, append to `context.md`, next round.
3. If none remain → enter phase 2.

If rounds exhaust with open questions (either mode) → **gate failure** (no
code produced); write `report.md` and stop.

### 2. Phase 2 — implement → verify → review

For each iteration until every reviewer required by the active mode approves
or iterations exhaust:

1. **Developer** (default implementation worker, not a named `agent`) —
   `developer-dispatch.md`. Only this worker may modify the repo.
2. **Verification** (parent): run the verify command from context (or
   `/manifest-code-quality:project-verify`). On failure, write deficiencies to
   `iterations/<n>/verify.log`, skip review dispatch, and send that output to
   the next developer iteration.
3. Generate review package: `git diff` + `git diff --cached` →
   `iterations/<n>/review-package.diff`.
4. Dispatch reviewers for the active mode in one OMP `task` batch:
   - **standard:** developer reviewer (`reviewer`) only.
   - **high-assurance:** developer reviewer and architecture critic
     (`reviewer`), and QA critic (`security-reviewer`).
5. Parse verdicts per `prompts/verdict-format.md`. A verdict counts as an
   approval only when its `role` matches the dispatched persona, it is a
   well-formed `cddl-verdict` block scoped to this iteration, verification
   (step 2) passed, and every acceptance criterion in `context.md` is
   satisfied — a malformed/missing verdict, wrong persona, failed
   verification, unsatisfied acceptance criterion, or stale (prior-iteration)
   verdict is **never** an approval. If **any** required persona has findings
   or fails to approve → merge findings into `iterations/<n>/findings.md` for
   the next developer dispatch.
6. If **every** reviewer required by the active mode `approve`s with **empty
   findings** on this iteration → success (step 3).

If iterations exhaust without full approval → **ceiling failure**; leave work
applied but **unstaged**; `report.md` lists per-persona outstanding findings.

### 3. Success disposition

- `git add --` only paths from the final approved iteration (never
  pre-existing dirt, never unrelated files).
- **Never** commit, push, or merge.
- Write `report.md`; tell the operator staged paths (`git diff --cached --name-only`).

## Operator relay (phase 1)

When critics or the orchestrator ask questions, present them conversationally,
collect answers in one message, persist to `answers-<round>.md`, and continue
— one continuous session. Do not ask the operator to run CLI tools.

## Headless API boundary

`../../runtime/cddl/cddl_invoke.py` remains available to programmatic,
noninteractive callers that need one stdin-driven provider invocation. Its
`CDDL_INVOKE_PROVIDER` and `CDDL_INVOKE_CLI` controls apply only to that API;
they never replace OMP `task` in this interactive loop, and it has no
`--assurance` flag — assurance mode selection belongs to this skill's
interactive orchestration only.

## Persistence

Per iteration: `developer-report.md`, `developer-reviewer.md`, and — in
high-assurance mode only — `qa-critic.md`, `arch-critic.md`; plus
`verdicts.json` (parsed), `verify.log`, `findings.md`.

**Same-iteration identity.** A persona's verdict is scoped to the iteration
number in its own artifact path (`iterations/<n>/<role>.md`) and the diff
recorded there (`iterations/<n>/review-package.diff`). It satisfies gating
only for that iteration. If the developer produces a new candidate at
iteration `n+1`, every verdict recorded at `iterations/<=n>/` is stale and
must be re-collected against the new diff — even one whose `decision` was
`approve`.

Keep everything under the run dir (manual prune: `rm -rf <run-id>`).

## What this skill does NOT do

- Use the cross-model parallel-review interface for personas
- Let critics or the developer reviewer write code
- Commit or push
- Accept a stale, role-mismatched, or malformed verdict as approval
- Silently reclassify a resumed run's assurance mode
