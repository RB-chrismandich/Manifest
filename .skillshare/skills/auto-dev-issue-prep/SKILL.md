---
name: auto-dev-issue-prep
description: Triage/groom/prep a single issue for the auto-dev loop — apply the `auto-dev` label when ready, or tighten scope and draft clarifying questions when not. Use before auto-issue-dev when asked to assess, make-ready, or validate an issue for autonomous development.
---

# Auto-Dev Issue Prep

Get **one** issue ready for `auto-issue-dev` — the autonomous developer that picks up
`auto-dev`-labeled issues and implements them test-first with no human in the loop. Because
that developer has no one to ask mid-task, an issue is only safe to hand it when the goal,
scope, and definition of "done" are unambiguous **from the issue alone**. This skill makes
that readiness call and closes the gap when it's missing.

Analysis-first by design: it never silently mutates. It reports a verdict and shows the
exact label / description edit / comment it proposes, then applies changes only on your
confirmation — or autonomously with `--apply` for unattended backlog grooming.

## When to use

- "Is #123 ready for auto-dev?" / "Can the bot take this one?"
- "Prep / groom this issue for autonomous development."
- "Improve this issue so auto-dev can pick it up."
- Before a backlog sweep that will label issues for the autonomous loop.

## Procedure

1. **Load the issue.** Run
   `configs/claude/scripts/git_ops.sh issue-view <N> --json number,title,body,state,labels,comments`.
   If no number is given, use the one in context or ask which issue.

2. **Score against the readiness rubric.** Each item is a concrete way the autonomous
   developer could stall or build the wrong thing — that's *why* it gates labeling:
   - **Testable acceptance criteria** — a checkable definition of done. Test-first
     development has nothing to anchor on without it.
   - **Bounded scope** — one cohesive change, not an epic or a vague "improve X".
     Oversized scope yields sprawling, unreviewable PRs.
   - **Self-contained** — completable with no human judgment, product/design decision,
     secret, or manual/external access. These are hard blocks: the bot cannot acquire them.
   - **Dependencies resolved** — no unmet "depends on / blocked by / requires / needs #N"
     (the `auto_issue_dev.sh` selector parses these and would skip the issue anyway).
   - **Reproducible context** — bugs carry repro steps + expected/actual; features name the
     target surface and the intended behavior.

3. **Decide a verdict:**
   - **READY** — rubric clears. Recommend the `auto-dev` label; on confirmation apply
     `git_ops.sh issue-edit <N> --add-label auto-dev`.
   - **NEEDS-PREP** — real work, but under-specified. Draft a tighter issue body (sharper
     title, explicit acceptance criteria, scope boundaries, test notes) and/or the fewest
     clarifying questions that would unblock automation. Do **not** label `auto-dev` yet.
   - **NOT-SUITABLE** — needs something the bot can't supply (human judgment, secrets,
     external access, an unresolved design decision). Explain why; recommend it stays
     human-owned.

4. **Close the gap (NEEDS-PREP):**
   - If the missing detail is knowable from the repo/issue, propose a rewritten description
     and, on confirmation, update it: `git_ops.sh issue-edit <N> --body "<improved>"`.
     **Preserve the reporter's intent and content — tighten, don't replace.**
   - If it needs the reporter's input, draft the questions and, on confirmation, post them:
     `git_ops.sh issue-comment <N> --body "<questions>"`. If the reporter is in this session, just
     ask inline instead of commenting.
   - Re-score once answers land; promote to READY when the rubric clears.

5. **Report** using the template below: verdict, per-rubric result, and the exact proposed
   action shown *before* it is applied.

## Output template

ALWAYS use this structure so the verdict and the proposed mutation are unambiguous:

```text
## Issue #<N> — <READY | NEEDS-PREP | NOT-SUITABLE>
**Title:** <title>

| Rubric | Status | Note |
|--------|--------|------|
| Testable acceptance criteria | ✅ / ⚠️ / ❌ | <one line> |
| Bounded scope                | ✅ / ⚠️ / ❌ | <one line> |
| Self-contained               | ✅ / ⚠️ / ❌ | <one line> |
| Dependencies resolved        | ✅ / ⚠️ / ❌ | <one line> |
| Reproducible context         | ✅ / ⚠️ / ❌ | <one line> |

**Rationale:** <one short paragraph>
**Proposed action:** <add `auto-dev` label | update description (show the new body) | post clarification (show the text) | keep human-owned>
```

## Notes

- **Mutations are confirmed, not assumed.** Default to proposing and applying on a clear
  go-ahead. `--apply` enables unattended grooming (e.g. a backlog sweep): in that mode apply
  READY labels and description improvements automatically, but still only *post* questions —
  never invent answers on the reporter's behalf.
- **Redact** secret-shaped content before posting a comment or editing a body (use
  `audit_log.sh redact` when writing through a script path).
- **Fail-open on writes:** a failed label/edit/comment is reported plainly, never silently
  swallowed, and never leaves an issue half-groomed without saying so.
- **One issue per invocation.** To sweep the backlog, the caller loops this over
  `git_ops.sh issue-list`; keeping the unit small keeps each readiness call auditable.
- This is the **intake** step; `auto-issue-dev` is the **development** step. Labeling an
  issue `auto-dev` here is the signal that hands it to that loop, so treat the label as a
  commitment that the rubric genuinely cleared.
