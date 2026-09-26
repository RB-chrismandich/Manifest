# Spec Artifact Discovery (speckit ⇄ design-doc)

Read-on-demand reference (NOT auto-loaded). The spec-* skills that read planning
artifacts (`spec-review`, `spec-audit-tasks`, `spec-decide-tradeoffs`) link here
instead of each hardcoding one workflow's paths. Indexed from
this bundle reference index. The executable implementation of
this contract is `discover_artifacts()` / `resolve_artifacts()` in
`../spec_review.sh`.

## The two supported layouts

A project uses **one** of these. Discovery must detect which, not assume speckit.

| Role | speckit | design-doc |
|---|---|---|
| **spec** | `specs/<NNN-slug>/spec.md` (newest by name sort), else `./spec.md` | newest `docs/design/specs/*-design.md` (date-prefixed) |
| **plan** | `plan.md` beside the spec | newest `docs/design/plans/*.md` |
| **tasks** | `tasks.md` beside the spec | **none** — tasks are embedded in the plan |
| prereqs | none — `specs/<NNN-slug>/` directories are self-contained | no tooling; artifacts are plain dated markdown |

**Consequence for the cross-reference:** speckit is three-way **spec ↔ plan ↔ tasks**;
the design-doc layout is two-way **spec ↔ plan (+ embedded tasks)**. A skill MUST NOT
report a "missing tasks.md" finding in a design-doc project — parse the plan's task
list instead.

## Discovery precedence

1. **Explicit paths win.** If the caller passed `--spec` / `--plan` / `--tasks` (or the
   skill was given paths), use exactly those; discover nothing.
2. **speckit next.** If a `specs/<n>/spec.md` (or `./spec.md`) exists, treat it as
   speckit: emit `spec`/`plan`/`tasks` from the spec's directory. Discovery is plain
   globbing — there is no scaffolding or resolver script; the `specs/` directories
   are self-contained.
3. **design-doc fallback.** Else emit the newest `docs/design/specs/*-design.md` as
   `spec` and the newest `docs/design/plans/*.md` as `plan`. Emit **no** `tasks` role.
4. **Nothing found.** Report that no planning artifacts were discovered and stop — never
   fabricate paths.

"Newest" = lexicographic name sort (`ls | sort | tail -1`); both layouts date-prefix files.

**File targets.** A ROOT that is a *file* (e.g. "point the command at the design doc",
feature 482 US3) is itself the `spec`, paired within its **own** layout tree: a path under
`docs/design/specs/` pairs the newest `docs/design/plans/*.md` from the same tree;
any other markdown file pairs sibling `plan.md`/`tasks.md`. A co-existing speckit layout
never hijacks an explicitly-targeted design doc (or vice versa).

## What each consumer does with the roles

- **spec-review** — cross-references the discovered roles for internal consistency
  (spec↔plan↔tasks, or spec↔plan for the design-doc layout). Delegates discovery to
  `spec_review.sh` (`resolve_artifacts` → `discover_artifacts`), a lightweight resolver that
  implements the **path-resolution subset** of this contract: explicit paths, else the newest
  `specs/*/spec.md` (speckit) or the newest `docs/design/*` (design-doc).
- **spec-audit-tasks** — audits that each task was genuinely completed. The task list comes
  from `tasks.md` (speckit) **or** the plan's embedded task list (design-doc). In speckit,
  the task list is `tasks.md` inside the spec's feature directory; in the design-doc layout,
  parse checkbox/numbered tasks out of the newest plan.
- **spec-decide-tradeoffs** — records the chosen option in the spec's Clarifications/Decisions
  section or `research.md` (speckit), **or** the design doc's Decisions section
  (`docs/design/specs/*-design.md`) for the design-doc layout, keeping entity/field names
  consistent with the surrounding artifact set.

## Reusing the shell seam

`../spec_review.sh` exposes the discovery as composable functions that
emit `role<TAB>path` lines — `resolve_artifacts [ROOT]` (honors `$SPEC`/`$PLAN`/`$TASKS`,
else `discover_artifacts`). A skill that needs the same resolution in shell should source or
shell out to these rather than re-deriving the globs, so the layout rules live in exactly one
place.
