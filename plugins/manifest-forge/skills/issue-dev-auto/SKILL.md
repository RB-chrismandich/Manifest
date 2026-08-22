---
name: issue-dev-auto
description: "Autonomously develop one opted-in ('auto-dev'-labeled) issue end-to-end: implement test-first and open a PR; a PR-monitoring loop tracks merge-readiness (merge is hard-gated here). Dependency-blocked issues are skipped. Run unattended via /loop /issue-dev-auto."
---

# Autonomous Issue Developer

Develop **exactly one** eligible issue per invocation, then stop. `/loop` re-runs
this skill with fresh context for the next issue.

## Critical Rules

1. **Automated merge is unavailable in this plugin distribution — the develop
   step stops at PR-open, full stop.** Two adversarial CDDL review rounds found
   the merge machinery unsound: the concurrency lock (`../../runtime/bin/loop_lock.sh`)
   is known-inert in production (GitHub's `--add-label` only attaches
   pre-provisioned labels; `labels.yml` provisions only the static
   `loop-active`, never the dynamic `loop-active:<epoch>:<token>` lease the
   lock actually requests — a passing test used a seam that accepted arbitrary
   label names, a false green), plus six further open findings (no global
   merge serialization, no `--match-head-commit`, the sink not re-checking
   `reviewDecision`, and more). `../../runtime/bin/pr_merge_loop.sh merge` therefore
   **hard-refuses unconditionally** (exit 78) in this bundle — `PR_MERGE_LOOP_APPLY=1`
   does **not** re-enable it; the gate is not an env toggle. The rest of the
   pipeline is unaffected and still runs: signal-gathering, the merge decision
   logic (`../../runtime/bin/merge_decision.sh`), and PR-tracking/reporting all work
   normally and still require every clear condition (CI green, no actionable
   human comment, `/manifest-forge:pr-review`=merge, `/manifest-code-quality:project-verify`
   pass, #360 gate Tier-1 pass, consensus ≥ 0.80) before a PR is even
   *reported* as merge-ready — a human performs the actual merge. See
   the Manifest marketplace-restructure design spec (§4, in the Manifest source repository — not shipped in this bundle)
   Phase 1 item 1.3 for the full finding and the separate safety spec this is
   pending on.
2. **Never touch issues lacking the `auto-dev` label.** Selection is opt-in.
3. **One issue per invocation.** Do not loop inside this skill.
4. **On failure, open a DRAFT PR** (no `Closes` keyword) so a human can inspect
   partial work — never a real PR. If there are no commits, skip the draft.
5. Status sync (`planned→in-progress→needs-review`) and `Closes #N` are handled by
   the issue-linking hooks — do not hand-edit labels for the happy path.

## Session model

This skill is **long-horizon**: one invocation develops an issue end-to-end (implement, test, PR), and it is
designed to run unattended under `/loop`.

This skill runs on the session default, Opus (1M context) — the top tier, so there is
nothing to switch to. It used to ask the user to move to Fable 5 first; that tier was
retired 2026-08-17 (rationale in `docs/MODEL-POLICY.md`).

## Procedure

1. **Preflight.** Ensure the issue hooks are enabled:
   `../../runtime/bin/install_issue_hooks.sh --enable` (idempotent). Confirm
   `gh`/`glab` is authenticated.
2. **Select.** Run:
   `../../runtime/bin/auto_issue_dev.sh next-issue --json`
   - Exit 3 ⇒ read `skipped_dependency`/`skipped_other` from the JSON, announce
     "eligible queue empty — stopping (skipped N dependency-blocked)", and END.
   - Exit 0 ⇒ parse `{number,title,url,skipped_dependency}`; call the issue `#N`.
3. **Branch.** `git switch -c <N>-<short-slug>` (numeric prefix links `#N`).
4. **Develop test-first.** Invoke `superpowers:test-driven-development`: write a
   failing test for the issue's acceptance criteria, implement minimally, get green.
   Keep scope to the issue.
5. **Verify.** Run `/manifest-code-quality:project-verify`. Lint warnings are non-blocking; test or security
   failures are blocking.
6. **Outcome:**
   - **Success** → `../../runtime/bin/git_ops.sh pr-create --title "<...>" --body "<...>"`.
     The PR hook injects `Closes #N` and moves `#N` to `needs-review`. **Stop.**
   - **Failure/stuck** → push WIP and open a **draft**:
     `git_ops.sh pr-create --draft --title "[WIP] <...>" --body "Partial; needs human."`
     then `auto_issue_dev.sh mark-blocked <N> "<one-line reason>"`.
7. **Audit.** After determining the outcome, append one record to the audit log:

   ```bash
   ../../runtime/bin/audit_log.sh append \
     "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"issue\":N,\"action\":\"<pr-opened|draft-pr|blocked>\",\"outcome\":\"<PR #NNN or draft or blocked: reason>\",\"reason\":\"<selection reason>\",\"skipped_dependency\":K}"
   ```

   The script redacts secrets before writing and fails open — a write failure never blocks the run.
8. **Summary.** Print one line: issue, outcome (PR # or draft), and skip count.

## PR Monitoring & Merge Loop (extends, does not replace, the develop flow — FR-016)

**Automated merge is unavailable in this plugin distribution.** See Critical Rule 1 and
the Manifest marketplace-restructure design spec (§4 Phase 1 item 1.3, in the Manifest
source repository — not shipped in this bundle) for the full finding (inert concurrency
lock, a false-green test, six further open findings) and the separate safety spec it is
pending on. The decision logic below is **not removed and still runs** — only
`pr_merge_loop.sh merge` (and any `tick` path that would reach it) hard-refuses,
unconditionally, regardless of `PR_MERGE_LOOP_APPLY`.

Everything below is scoped to **this bundle's vendored runtime**
(`../../runtime/bin/*`) only. The Manifest source repository (not shipped in
this bundle) separately maintains its own bootstrap-deployed copy of this same
loop, outside `plugins/`, for the coordinator's own self-hosted use — that
copy is independently maintained, is currently **regressed to fully inert
`tick`/`run`** (it received the same lock-ownership hardening described in
step 2 below, but not the compensating DEGRADED-proceed fix, because unlike
this bundle its `cmd_merge` is not hard-gated and cannot safely proceed
without a working lock), and none of the DEGRADED/CONTENDED exit-code
behavior this section documents applies to it. See the marketplace-restructure
design spec's §4 1.3 "third CDDL developer-reviewer finding" correction for
the accurate account — it is not "unaffected" or "unchanged," it is a known,
deliberate, fail-closed regression pending the same safety spec.

After the develop→PR step, the same loop tends the open **managed** PRs (automation-authored;
see `../../runtime/config/automation_authors.json`). This is self-paced and bounded, and it uses the
deterministic primitives so the (currently gated) irreversible step is never a judgment call:

1. **List managed PRs.** `../../runtime/bin/pr_merge_loop.sh list-managed --json` (humans are skipped — FR-013).
2. **Per PR, compute signals + decide.**
   `../../runtime/bin/pr_merge_loop.sh signals <pr> --json | ../../runtime/bin/merge_decision.sh decide`
   returns `{action}` — one of `merge | revise | wait | update-branch | hand-human | halt`.
   Take the lock first: `../../runtime/bin/loop_lock.sh acquire <pr>`. Its exit code is not a
   plain success/fail — `1` means CONTENDED (a live lease held by someone else, a lost race,
   or same-host `flock` contention) and still skips the PR this pass; `2` means DEGRADED (the
   lease could not even be attempted — the backend rejects the unprovisioned dynamic
   `loop-active:<epoch>:<token>` label, per `labels.yml`) and is
   **not** evidence of contention, so `cmd_tick` proceeds without the cross-host lock rather
   than skipping (merge is hard-gated elsewhere, so nothing irreversible depends on this lock
   — its only remaining job is avoiding duplicated run-gate work). Release in all paths
   regardless of which code was returned (release is idempotent).
3. **Act on the action:**
   - `revise` → run one cycle: `/manifest-forge:pr-address-comments`, then `/manifest-code-quality:project-verify`,
     then `/manifest-forge:pr-review`
     (fan independent reviews out in parallel — FR-015); push; `../../runtime/bin/pr_merge_loop.sh address-cycle <pr>`
     records the revision. After **3** cycles without clearing, the decision returns
     `hand-human` → label `needs-human`, move on (FR-005/006).
   - `wait` → checks/mergeability still settling; end this PR's turn and re-check next run
     (self-paced; never block past the 10-minute ceiling — FR-017).
   - `update-branch` → one `gh pr update-branch`; re-read; `DIRTY`/conflict → `needs-human`.
   - `hand-human` → apply the decision's `label` (`needs-human` or `ready-to-merge`) and skip.
   - `halt` → main CI went red after a merge: **stop the whole loop**, flag for a human (FR-012a).
   - `merge` → the decision layer still reaches this verdict once the #360 verification
     gate passes (Tier-1) and consensus is high — `../../runtime/bin/pr_merge_loop.sh tick <pr>`
     runs the gate and re-decides normally. But the sink, `cmd_merge`, hard-refuses
     unconditionally in this bundle (exit 78) before touching admin pre-flight or
     `gh pr merge` at all — see the section intro above. `PR_MERGE_LOOP_APPLY` has **no
     effect** on this; a PR that reaches `merge` is reported (`needs-human`) for a
     human to merge manually, never merged by the loop itself.
4. **Loop control.** Run one bounded pass with `../../runtime/bin/pr_merge_loop.sh run`. It
   self-paces, enforces a hard 10-minute ceiling, acquires `loop_lock` per PR (one in
   flight; monitoring interleaves — FR-014, though the cross-host mutual-exclusion property
   this is meant to provide is not actually enforced in production — see step 2's DEGRADED
   case), resets the empty-run counter on work / increments on idle passes,
   and **stops after 5 consecutive empty runs** (FR-018/018a). Every PR that clears to
   `merge` surfaces for a human rather than being merged. `/loop /issue-dev-auto`
   remains the outer re-invoker that gives each pass fresh context.

Every action appends a redacted `../../runtime/bin/audit_log.sh` record (FR-021/022).

## Notes

- Dependency-blocked issues are detected and tagged `blocked-dependency` by
  `next-issue`; you never see them.
- This skill writes code (allowed tools include Edit/Write); keep diffs scoped to
  the selected issue.
- The merge decision logic is unit-tested offline (`tests/bats/merge_decision.bats`,
  `verification_gate.bats`, `pr_merge_loop.bats`) — it is a tested decision, not prose,
  even though the sink it used to feed is currently hard-gated (see above).
  `pr_merge_loop.bats` also carries dedicated coverage of the vendored copy's gate
  (`vendored: ...` tests) and, since 2026-08-20, dedicated `vendored REGRESSION: ...`
  tests proving `tick` both (a) still dispatches real work when the cross-host lease
  cannot be attempted (DEGRADED — proceeds) and (b) still declines when a lease is
  genuinely held by someone else (CONTENDED — blocks); see step 2 above for the
  exit-code contract. `loop_lock.bats` targets this same vendored `loop_lock.sh`
  and, per the finding above, several of its pre-fix tests are `skip`-marked (not
  left failing) against the faithful fake label backend, with the reason recorded
  inline — expected, not a regression to silence. `pr_merge_loop.bats`'s own lock
  stub used to accept any label name unconditionally too — the same false-green
  shape, not propagated from `loop_lock.bats` until 2026-08-20 — which is why the
  fail-closed `loop_lock.sh` fix silently made `tick`/`run` dead-on-arrival for a
  time without any test noticing; see the spec's §4 1.3 "Correction, 2026-08-20"
  block for the full account.
