---
name: issue-dev-auto
description: "Autonomously develop one opted-in ('auto-dev'-labeled) issue end-to-end: implement test-first and open a PR; an opt-in gated loop may also merge cleared PRs (dry-run by default). Dependency-blocked issues are skipped. Run unattended via /loop /issue-dev-auto."
---

# Autonomous Issue Developer

Develop **exactly one** eligible issue per invocation, then stop. `/loop` re-runs
this skill with fresh context for the next issue.

## Critical Rules

1. **Merge only through the verified gate (supersedes the former "never merge" rule).**
   The develop step still stops at PR-open. A PR is merged to main *only* by the
   PR-monitoring loop below, and only when every clear condition holds (CI green, no
   actionable human comment, `/manifest-forge:pr-review`=merge, `/manifest-code-quality:project-verify` pass, #360
   gate Tier-1 pass, and
   consensus ≥ 0.80) — a tested decision (`merge_decision.sh`), never a judgment call. Merges
   are **opt-in** (`PR_MERGE_LOOP_APPLY=1`); the default is dry-run. Anything short of fully
   clear → the PR goes to a human, never a partial/forced merge.
2. **Never touch issues lacking the `auto-dev` label.** Selection is opt-in.
3. **One issue per invocation.** Do not loop inside this skill.
4. **On failure, open a DRAFT PR** (no `Closes` keyword) so a human can inspect
   partial work — never a real PR. If there are no commits, skip the draft.
5. Status sync (`planned→in-progress→needs-review`) and `Closes #N` are handled by
   the issue-linking hooks — do not hand-edit labels for the happy path.

## Session model

This skill is **long-horizon**: one invocation develops an issue end-to-end (implement, test, PR), and it is
designed to run unattended under `/loop`.

Before starting, check the session's model. If it is not Fable 5, **ask the user to switch**
(`/model` → Fable 5) and wait for the answer. Do not assume Fable is active, and do not silently
proceed on the default model — the choice trades ~2x the per-token cost against capability, so it
is the user's to make. Everything shorter than this runs on Opus by default
(`session_model` in `command_config.yml`; rationale in `docs/MODEL-POLICY.md`).

## Procedure

1. **Preflight.** Ensure the issue hooks are enabled:
   `configs/claude/scripts/install_issue_hooks.sh --enable` (idempotent). Confirm
   `gh`/`glab` is authenticated.
2. **Select.** Run:
   `configs/claude/scripts/auto_issue_dev.sh next-issue --json`
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
   - **Success** → `configs/claude/scripts/git_ops.sh pr-create --title "<...>" --body "<...>"`.
     The PR hook injects `Closes #N` and moves `#N` to `needs-review`. **Stop.**
   - **Failure/stuck** → push WIP and open a **draft**:
     `git_ops.sh pr-create --draft --title "[WIP] <...>" --body "Partial; needs human."`
     then `auto_issue_dev.sh mark-blocked <N> "<one-line reason>"`.
7. **Audit.** After determining the outcome, append one record to the audit log:

   ```bash
   configs/claude/scripts/audit_log.sh append \
     "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"issue\":N,\"action\":\"<pr-opened|draft-pr|blocked>\",\"outcome\":\"<PR #NNN or draft or blocked: reason>\",\"reason\":\"<selection reason>\",\"skipped_dependency\":K}"
   ```

   The script redacts secrets before writing and fails open — a write failure never blocks the run.
8. **Summary.** Print one line: issue, outcome (PR # or draft), and skip count.

## PR Monitoring & Merge Loop (extends, does not replace, the develop flow — FR-016)

After the develop→PR step, the same loop tends the open **managed** PRs (automation-authored;
see `config/automation_authors.yml`). This is self-paced and bounded, and it uses the
deterministic primitives so the irreversible step is never a judgment call:

1. **List managed PRs.** `pr_merge_loop.sh list-managed --json` (humans are skipped — FR-013).
2. **Per PR, compute signals + decide.** `pr_merge_loop.sh signals <pr> --json | merge_decision.sh decide`
   returns `{action}` — one of `merge | revise | wait | update-branch | hand-human | halt`.
   Take the lock first: `loop_lock.sh acquire <pr>` (skip if held), release in all paths.
3. **Act on the action:**
   - `revise` → run one cycle: `/manifest-forge:pr-address-comments`, then `/manifest-code-quality:project-verify`,
     then `/manifest-forge:pr-review`
     (fan independent reviews out in parallel — FR-015); push; `pr_merge_loop.sh address-cycle <pr>`
     records the revision. After **3** cycles without clearing, the decision returns
     `hand-human` → label `needs-human`, move on (FR-005/006).
   - `wait` → checks/mergeability still settling; end this PR's turn and re-check next run
     (self-paced; never block past the 10-minute ceiling — FR-017).
   - `update-branch` → one `gh pr update-branch`; re-read; `DIRTY`/conflict → `needs-human`.
   - `hand-human` → apply the decision's `label` (`needs-human` or `ready-to-merge`) and skip.
   - `halt` → main CI went red after a merge: **stop the whole loop**, flag for a human (FR-012a).
   - `merge` → reachable only after the #360 verification gate passes (Tier-1) and consensus
     is high. `pr_merge_loop.sh tick <pr>` runs the gate, re-decides, and on `merge` does the
     admin pre-flight + `gh pr merge --squash --admin --delete-branch`, then `post-merge-check`.
     Honour `PR_MERGE_LOOP_APPLY` — default dry-run; set `=1` to perform real merges. Fail-closed
     exits (no admin / `enforce_admins` / `required_signatures`) route to `ready-to-merge` + human.
4. **Loop control.** Run one bounded pass with `pr_merge_loop.sh run` (set
   `PR_MERGE_LOOP_APPLY=1` for real merges; default dry-run). It self-paces, enforces a
   hard 10-minute ceiling, serializes merges via `loop_lock` (one in flight; monitoring
   interleaves — FR-014), resets the empty-run counter on work / increments on idle passes,
   and **stops after 5 consecutive empty runs** (FR-018/018a). It exits non-zero (11) if a
   merge reddens `main` (halt) so `/loop` surfaces the failure. `/loop /issue-dev-auto`
   remains the outer re-invoker that gives each pass fresh context.

Every action appends a redacted `audit_log.sh` record (FR-021/022).

## Notes

- Dependency-blocked issues are detected and tagged `blocked-dependency` by
  `next-issue`; you never see them.
- This skill writes code (allowed tools include Edit/Write); keep diffs scoped to
  the selected issue.
- The merge gate's safety logic is unit-tested offline (`tests/bats/merge_decision.bats`,
  `verification_gate.bats`, `loop_lock.bats`, `pr_merge_loop.bats`) — the irreversible merge
  is a tested decision, not prose.

- Dependency-blocked issues are detected and tagged `blocked-dependency` by
  `next-issue`; you never see them.
- This skill writes code (allowed tools include Edit/Write); keep diffs scoped to
  the selected issue.
