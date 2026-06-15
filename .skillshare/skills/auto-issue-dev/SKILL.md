---
name: auto-issue-dev
description: |
  Autonomously develop one opted-in ('auto-dev'-labeled) issue end-to-end: pick the
  next ready issue, implement test-first, and open a PR for review (never merges).
  Dependency-blocked issues are skipped. Run unattended via /loop /auto-issue-dev.
---

# Autonomous Issue Developer

Develop **exactly one** eligible issue per invocation, then stop. `/loop` re-runs
this skill with fresh context for the next issue.

## Critical Rules

1. **Never merge.** Stop at PR-open; a human reviews and merges.
2. **Never touch issues lacking the `auto-dev` label.** Selection is opt-in.
3. **One issue per invocation.** Do not loop inside this skill.
4. **On failure, open a DRAFT PR** (no `Closes` keyword) so a human can inspect
   partial work — never a real PR. If there are no commits, skip the draft.
5. Status sync (`planned→in-progress→needs-review`) and `Closes #N` are handled by
   the issue-linking hooks — do not hand-edit labels for the happy path.

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
5. **Verify.** Run `/verify`. Lint warnings are non-blocking; test or security
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

## Notes

- Dependency-blocked issues are detected and tagged `blocked-dependency` by
  `next-issue`; you never see them.
- This skill writes code (allowed tools include Edit/Write); keep diffs scoped to
  the selected issue.
