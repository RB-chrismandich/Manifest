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

- Prepare or read an issue with `manifest-forge:issue-prep-auto`.
- Mark implementation active with `manifest-forge:issue-sync-commit`.
- Publish review/ready state with `manifest-forge:issue-sync-pr`.
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
2. When the work is security sensitive, architectural, critical, or likely to
   change at least three files, dispatch independent planning proposals in one
   OMP `task` call (in waves of at most 32). Use `security-reviewer` for
   security-sensitive review and omit `agent` for implementation-oriented
   planning proposals. Children execute only their assigned unit and never
   re-dispatch.
3. Directly merge compatible structured proposals: preserve each proposal's
   evidence, risks, deliverables, and completion criteria. If incompatible
   recommendations remain load-bearing, dispatch one read-only OMP
   `reviewer` to adjudicate them from the proposals and evidence. If its
   recommendation still leaves a load-bearing choice unresolved, present the
   alternatives and evidence to the user. Do not use percentage bands,
   text-overlap consensus, or a synthesis CLI.
4. If `task` is unavailable, develop the proposals inline and report
   `DEGRADED`.
5. Write a date-prefixed plan below `$PLAN_ROOT` with Objective, Context,
   Deliverables, Related Files, Risks, Completion Criteria, and Log sections.
6. Present the plan for approval. For an issue-linked plan, request the
   `planned` state through the Forge interface.

### review

Review one named plan or all active plans. Report progress, age, and whether a
plan should be archived or abandoned. Re-evaluate stale plans with direct
read-only evidence review: use one OMP `reviewer` where independent evaluation
is needed, or work inline. If `task` is unavailable, report `DEGRADED`.

### execute

1. Resolve a named plan below `$PLAN_ROOT`, or an issue-linked plan matching
   `*issue-N*`. Ask when ambiguous.
2. Require `**Status**: ACTIVE` and request the in-progress tracker state through
   `manifest-forge:issue-sync-commit` when issue-linked.
3. Implement unchecked deliverables in order, updating the plan and its log
   after each completed item. Propagate failures and ask whether to retry, skip,
   or abort.
4. Before final issue-linked state mutation, obtain a read-only OMP `reviewer`
   review of the completed work and its evidence; retain sequential mutation
   after that review. If `task` is unavailable, review inline and report
   `DEGRADED`. Publish the result through `manifest-forge:issue-sync-pr`.
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
`../../runtime/references/sub-agent-dispatch.md`. Dispatch all independent
units in one OMP `task` call (in waves of at most 32); use `hub` only to
coordinate or wait. The parent validates and merges direct structured evidence.
Children execute their assigned unit and never re-dispatch. If `task` is
unavailable, complete the work inline and report `DEGRADED`.
