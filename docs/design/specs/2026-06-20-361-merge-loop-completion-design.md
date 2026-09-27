# #361 Auto-Dev Merge-Loop — Completion Design

**Date**: 2026-06-20
**Status**: Approved (design)
**Feature**: `361-auto-dev-merge-loop`
**Scope**: Close out the 6 remaining tasks (T003, T004, T011, T024, T026, T034) on an
otherwise-complete branch (30/36 tasks done, 64 tests green).

---

## Context

The #361 build is functionally complete: `merge_decision.sh` (pure decision core),
`loop_lock.sh` (serialization), `pr_merge_loop.sh` (signals/tick/merge/empty-run),
the verification-gate wiring (#360), labels, the automation-author allowlist, and the
`auto-issue-dev` SKILL orchestration all exist and pass their suites. Six tasks remain.
A review found that two of them are coupled and one masks a real safety gap. This design
records the decisions that close them.

---

## Decisions

### T026 — `run` loop driver lives in the script (not skill prose)

Add a thin `run` subcommand to `pr_merge_loop.sh` that owns the **hard per-run ceiling**
and self-paced pass. `/loop /auto-issue-dev` remains the outer re-invoker (fresh context
per pass); the script owns the bounded safety limit.

**Why:** a "hard" ceiling enforced only by a sentence in SKILL.md is soft — subject to
model judgment. A wall-clock check in code is the only thing that makes it hard. It also
unblocks T024 (a clock-seam ceiling test needs a code path that reads the clock).

```
pr_merge_loop.sh run [--apply]
  deadline = now() + CEILING_SECONDS        # clock behind the existing seam
  while now() < deadline:
    did_work = false
    for pr in list-managed:
      if now() >= deadline: break           # hard ceiling, checked between PRs
      act = tick pr                          # lock, signals, decide, (gate), act
      if act not in {skip, wait}: did_work = true
      if act == halt: exit                   # main went red post-merge
    if did_work: empty-run reset
    else: empty-run incr; if empty-run get >= 5: break
  # exit cleanly at ceiling / 5-empty / halt
```

- Ceiling default surfaced as `PR_MERGE_LOOP_CEILING_SEC` (default 600). Clock read
  through the existing seam used by the bats suite so T024 can fast-forward it.
- Reuses existing primitives only — no new decision logic.
- SKILL.md (T028) is reconciled to **call `run`** rather than re-describe the loop steps,
  removing the prose/code duplication.

**Exit codes (so the ceiling is observable, not just enforced):**
- ceiling reached / 5-empty stop → exit **0** (normal, expected termination).
- `halt` (main went red post-merge) → exit **non-zero** (dedicated code, e.g. `11`) so the
  outer `/loop` re-invoker or a CI runner immediately flags the failure instead of silently
  re-entering. `merge`/network failures that route a single PR to `needs-human` do **not**
  fail the whole run.

**Per-call timeout (so a hang can't bust the hard ceiling):** the between-PR deadline check
cannot interrupt a `tick` already blocked on a hanging network call. Every network accessor
in `gh_op` must run under an explicit timeout (wrap `gh`/`glab`/`curl` with the repo's
`timeout` helper from `bootstrap/lib/platform.sh`, or `gh --timeout` where available), so a
single stuck call fails fast and the loop's wall-clock bound stays hard.

### T004 — wire the real GraphQL review-thread accessor, inline, fail-closed

Replace the `unresolved-human) echo 0` stub in `pr_merge_loop.sh`'s `gh_op` with a real
GraphQL query for unresolved review threads.

**Why:** today an unresolved human review thread that is *not* a formal
`CHANGES_REQUESTED` never sets `review_block`, so the loop could merge over an open review
comment — fail-**open**, the opposite of the spec's intent. The passing seam test
(`SEAM_UH=2`) only exercises the classifier math, not the (missing) production query, giving
false confidence.

- Query: `reviewThreads(first:100){ isResolved, isOutdated, comments(first:1){ nodes{ author{ login } } } }`.
  Count threads where `isResolved == false && isOutdated == false`. Human-authored unresolved
  threads block; bot-authored nits (allowlisted bot logins) remain **advisory**, per research.md R2.
- On query error **or any missing / structurally malformed payload**, return a conservative
  non-zero (fail-closed) so a GraphQL failure does not silently unblock a merge. The parser
  treats absent fields as "unresolved present," not "none."
- The advisory bot allowlist is read from the existing `config/automation_authors.yml`
  (the bot-login set), **not** hardcoded into the `jq`/parse expression, so it stays updatable
  in one place.
- **Location:** stays inline in `gh_op` alongside `checks`/`reviewdecision`/`mergeable`/
  `protection`, with the GitLab branch beside it — consistent with every other accessor.
  T004's task text (which said `git_ops.sh`) is reconciled to "inline in pr_merge_loop.sh";
  no other script consumes review-thread state, so the speculative-reuse case for git_ops.sh
  does not apply (YAGNI).

### T011 — address-cycle tests

Add bats cases (injected-seam pattern already in the suite) for `address-cycle`:
runs `/address-pr-comments` → `/verify` → `/pr-review` from fixtures, asserts
`revisions_used` increments, returns `revise` under budget, and flips to `hand-human`
with the `needs-human` label at budget exhaustion.

### T024 — empty-run + ceiling tests (now writable via T026)

Add bats cases:
- **Accounting (FR-018/018a):** a pass that saw an in-flight PR counts as work → `reset`;
  a fully-idle pass → `incr`; the loop stops at 5 consecutive empties.
- **Ceiling:** with the `run` driver present, advance the clock seam past the deadline and
  assert the run terminates at the boundary (checked between PRs, not mid-merge).

### T003 — live label provisioning (gated)

Run `label_sync.sh --dry-run` first, show the diff, then run the real sync **only on
explicit go-ahead**. Idempotent and low-risk (adds `ready-to-merge`, `loop-active`, `hold`)
but it mutates the live GitHub repo, so it is never run silently. When the three labels
already exist as intended, the dry-run must report `No changes required` and exit cleanly
(no forced prompt), so future unattended bootstrap runs are smooth.

### T034 — deferred (environment-blocked)

`signals <pr> | decide` dry-run needs a live PR; none exists (branch is local-only, no open
automation PR). **Defer** with a tasks.md note: run when the #361 PR (or any automation PR)
first exists. Keeps "code complete + green" separate from "live." Opening the PR is a
separate deliberate push step.

The tasks.md note spells out the exact verification recipe so it is unambiguous when picked
up later:

```
# After pushing 361-auto-dev-merge-loop:
gh pr create --base main --head 361-auto-dev-merge-loop \
  --title "feat: auto-dev merge loop (#361)" --body "Closes #361"
# Then dry-run (no mutation — signals/decide never write):
configs/claude/scripts/pr_merge_loop.sh signals <PR> --json \
  | configs/claude/scripts/merge_decision.sh decide
# Expect a single {action} object; confirm `gh pr view <PR>` shows no label/state change.
```
Note: a human-authored PR is skipped by `list-managed`, but `signals <pr>` works against any
PR number, so it is valid for the smoke test.

---

## Out of scope

- Pushing the branch / opening the #361 PR (separate deliberate step).
- Any change to the decision core, lock, or gate (already complete and green).
- GitLab auto-merge parity beyond the existing fail-closed stubs.

---

## Verification

1. `shellcheck configs/claude/scripts/{pr_merge_loop,merge_decision,loop_lock}.sh` clean.
2. `yamllint` any edited `configs/claude/config/*.yml` clean.
3. `bats tests/bats/{merge_decision,loop_lock,pr_merge_loop}.bats` fully green, including the
   new T011 + T024 cases.
4. New tests fail before their implementation (TDD ordering) — especially the T004
   fail-closed-on-error case and the T024 ceiling case.
5. Every variable in the new `run` loop is `local` (no state bleed across iterations);
   shellcheck's SC2030/SC2031 and scoping warnings stay clean.

## Task disposition summary

| Task | Outcome |
|------|---------|
| T003 | Dry-run preview → real sync on go-ahead (live mutation, gated) |
| T004 | Real GraphQL review-thread accessor, inline, fail-closed; text reconciled |
| T011 | Address-cycle bats cases added |
| T024 | Empty-run accounting + clock-seam ceiling cases added (unblocked by T026) |
| T026 | `run` subcommand with hard wall-clock ceiling; SKILL.md calls it |
| T034 | Deferred with a note (needs a live PR) |
