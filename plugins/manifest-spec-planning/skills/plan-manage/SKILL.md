---
name: plan-manage
description: Manage XDG-backed plan lifecycle with create, review, execute, archive, and abandon flows, plus optional cross-agent review.
---

# Plan Management

Manage plans without coupling them to an assistant home. At the start of every
action, resolve the store from the skill directory:

```bash
PLAN_ROOT="$(python3 ../../runtime/plan_store.py --project-root "$PWD" --create)"
```

The default is `${XDG_DATA_HOME:-$HOME/.local/share}/manifest/plans`. A project
may opt into a committed local store only by adding `.manifest/plans.yml` with
one safe, project-relative entry such as `plan_root: .plans`. Never create that
setting on the user's behalf and never write project plan files without it.
The resolver creates `.archive/` and `.abandoned/` only inside the selected
store.

## Arguments

- `<action>`: `list`, `create`, `review`, `execute`, `archive`, or `abandon`
- `<description>`: required for text-based `create`
- `<filename>`: required for `execute`; optional for review/archive/abandon
- `<issue-number>`: `42` or `#42` for issue-linked create/execute

## Tracker Boundary

All issue reads, comments, labels, and closes go through qualified Forge skill
interfaces. Never locate or invoke a Forge runtime script directly.

- Prepare or read an issue with `[[skill:manifest-forge:issue-prep-auto]]`.
- Mark implementation active with `[[skill:manifest-forge:issue-sync-commit]]`.
- Publish review/ready state with `[[skill:manifest-forge:issue-sync-pr]]`.
- Use the canonical label definitions in `../../runtime/config/labels.json` when
  the Forge interaction asks for a label identity.

If the installed Forge interface cannot perform a requested mutation, report
`DEGRADED` and leave the tracker unchanged; do not bypass it with a home or
workspace path.

## Actions

### list

Read active `*.md` files in `$PLAN_ROOT`, excluding lifecycle children. Extract
filename, status, title, created date, and checked/total deliverables. Mark a
plan stale after seven days without modification.

### create

1. Resolve a plain description or use the qualified Forge preparation skill for
   an issue number.
2. Use `[[skill:manifest-workspace:parallel-agent]]` when the work is security
   sensitive, architectural, critical, or likely to change at least three files.
3. Merge proposals at 80%+ consensus. At 50-79%, dispatch one Sonnet synthesis
   sub-agent using `../../runtime/prompts/synthesis.md`. Below 50%, present the
   alternatives to the user.
4. Write a date-prefixed plan below `$PLAN_ROOT` with Objective, Context,
   Deliverables, Related Files, Risks, Completion Criteria, and Log sections.
5. Present the plan for approval. For an issue-linked plan, request the `planned`
   state through the Forge interface.

### review

Review one named plan or all active plans. Report progress, age, and whether a
plan should be archived or abandoned. A stale plan may be re-evaluated through
`[[skill:manifest-workspace:parallel-agent]]`.

### execute

1. Resolve a named plan below `$PLAN_ROOT`, or an issue-linked plan matching
   `*issue-N*`. Ask when ambiguous.
2. Require `**Status**: ACTIVE` and request the in-progress tracker state through
   `[[skill:manifest-forge:issue-sync-commit]]` when issue-linked.
3. Implement unchecked deliverables in order, updating the plan and its log
   after each completed item. Propagate failures and ask whether to retry, skip,
   or abort.
4. Run `[[skill:manifest-workspace:parallel-agent]]` for the final issue-linked
   review. Publish the result through `[[skill:manifest-forge:issue-sync-pr]]`.
5. On approval, mark the plan COMPLETED and move it to
   `$PLAN_ROOT/.archive/`. Otherwise leave it active with the findings recorded.

### archive

Require every deliverable to be checked, then move the plan to
`$PLAN_ROOT/.archive/`.

### abandon

Confirm with the user, record the reason, and move the plan to
`$PLAN_ROOT/.abandoned/`.

## Sub-agent dispatch

Use the bundle-local selection rules in
`../../runtime/references/sub-agent-dispatch.md`. Pin the create-flow synthesis
agent to Sonnet. Cross-model reviews use the qualified Workspace skill; no
shell command or sibling-bundle path is assumed.
