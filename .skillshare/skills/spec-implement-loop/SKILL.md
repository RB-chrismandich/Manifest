---
name: spec-implement-loop
description: Critic-gated implementation (CDDL) of a completed spec+plan — speckit feature dir or superpowers design doc. Two critics gate clarification, then an implementer iterates under project verification until dual structured approval stages the changes. Never commits or pushes.
---

# Critic-Gated Implementation Loop (CDDL)

Runs a completed feature's implementation through an adversarial two-phase loop:
a **clarification gate** (a QA/security critic and an architecture critic must both
independently signal no open questions) followed by an **implement → verify →
critique loop** that ends only on dual explicit approval or a bounded ceiling.
Success means changes are **staged, never committed** (staged = critic-approved)
on the current feature branch. This complements `/speckit-implement`; it does not
replace it or run its lifecycle hooks.

Prerequisites: a feature branch (not the default branch), a clean tree (or
explicit `--allow-dirty`), an authenticated `claude` CLI, and a resolvable
spec (+ optional plan) in either supported layout.

## Procedure

1. **Start** the run with the target path the user gave (feature dir, design doc
   root, or repo root — discovery follows the spec-artifact precedence):

   ```bash
   python3 ~/.claude/scripts/cddl_loop.py start <target-path> \
     [--spec <path>] [--plan <path>] [--verify-cmd '<cmd>'] \
     [--max-rounds N] [--max-iterations N] [--allow-dirty]
   ```

2. **Branch on the exit code** (stable contract):
   - **0** — success. Report the staged paths (`git diff --cached --name-only`)
     and the report location; remind the operator the loop never commits.
   - **3** — questions pending. Read the `questions.md` path from the output,
     relay each critic's questions to the operator conversationally, collect
     answers, write them to a temp file, then re-enter:

     ```bash
     python3 ~/.claude/scripts/cddl_loop.py answer --run <run-id> --answers-file <file>
     ```

     Repeat until the gate resolves (exit 0/4/5/7). This relay loop is the
     skill's main job — the operator experiences one continuous conversation.
   - **4** — gate failure: relay the unresolved questions from the report; the
     spec needs clarification work before implementation (no code was produced).
   - **5** — ceiling exhausted: summarize each critic's outstanding deficiencies
     from `report.md`; the candidate is applied but UNSTAGED with discard steps
     in the report.
   - **6** — pre-flight refusal: surface the one-line reason (branch, dirty
     tree, layout, roles, backend, lock) and how to fix it.
   - **7** — aborted (dead critic / timeout): point at the raw outputs under
     the run dir (`iterations/<n>/<role>.md`; phase-1 failures land in
     `clarify/round-<n>-<role>.md`) — every attempt is persisted.

3. **Inspect** on request: `cddl_loop.py status [--run <id>]` summarizes the
   latest run (blocking critic, top deficiency, run dir, report).

Runs persist under `${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/runs/<repo-slug>/`
(keep-everything; prune manually by deleting a run dir). Roles are tuned by
editing `configs/claude/prompts/cddl/*.md` in the Manifest repo and
redeploying — never edit the deployed copies.
