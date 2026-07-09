# Spec Artifact Discovery (speckit ⇄ superpowers)

Read-on-demand reference (NOT auto-loaded). The spec-* skills that read planning
artifacts (`spec-review`, `spec-audit-tasks`, `spec-decide-tradeoffs`) link here
instead of each hardcoding one workflow's paths. Indexed from
`configs/claude/CLAUDE.md` → "Reference Index". The executable implementation of
this contract is `discover_artifacts()` / `resolve_artifacts()` in
`configs/claude/scripts/spec_review.sh`.

## The two supported layouts

A project uses **one** of these. Discovery must detect which, not assume speckit.

| Role | speckit | superpowers |
|---|---|---|
| **spec** | `specs/<NNN-slug>/spec.md` (newest by name sort), else `./spec.md` | newest `docs/superpowers/specs/*-design.md` (date-prefixed) |
| **plan** | `plan.md` beside the spec | newest `docs/superpowers/plans/*.md` |
| **tasks** | `tasks.md` beside the spec | **none** — tasks are embedded in the plan |
| prereqs | `.specify/scripts/bash/check-prerequisites.sh` (+ `.specify/`, `extensions.yml` hooks) | no `.specify/`; artifacts are plain dated markdown |

**Consequence for the cross-reference:** speckit is three-way **spec ↔ plan ↔ tasks**;
superpowers is two-way **spec ↔ plan (+ embedded tasks)**. A skill MUST NOT report a
"missing tasks.md" finding in a superpowers project — parse the plan's task list instead.

## Discovery precedence

1. **Explicit paths win.** If the caller passed `--spec` / `--plan` / `--tasks` (or the
   skill was given paths), use exactly those; discover nothing.
2. **speckit next.** If a `specs/<n>/spec.md` (or `./spec.md`) exists — or a `.specify/`
   directory is present — treat it as speckit: emit `spec`/`plan`/`tasks` from the spec's
   directory. When `.specify/scripts/bash/check-prerequisites.sh` exists, prefer running it
   (`--json --paths-only` for path resolution, `--require-tasks --include-tasks` when a skill
   needs the task list) — it is the workflow's own authoritative resolver.
3. **superpowers fallback.** Else emit the newest `docs/superpowers/specs/*-design.md` as
   `spec` and the newest `docs/superpowers/plans/*.md` as `plan`. Emit **no** `tasks` role.
4. **Nothing found.** Report that no planning artifacts were discovered and stop — never
   fabricate paths.

"Newest" = lexicographic name sort (`ls | sort | tail -1`); both layouts date-prefix files.

## What each consumer does with the roles

- **spec-review** — cross-references the discovered roles for internal consistency
  (spec↔plan↔tasks, or spec↔plan for superpowers). Delegates discovery to
  `spec_review.sh` (`resolve_artifacts`), which implements this contract directly.
- **spec-audit-tasks** — audits that each task was genuinely completed. The task list comes
  from `tasks.md` (speckit) **or** the plan's embedded task list (superpowers). In speckit,
  resolve via `check-prerequisites.sh --json --require-tasks --include-tasks`; in superpowers,
  parse checkbox/numbered tasks out of the newest plan.
- **spec-decide-tradeoffs** — records the chosen option in the spec's Clarifications/Decisions
  section or `research.md` (speckit), **or** the design doc's Decisions section
  (`docs/superpowers/specs/*-design.md`) for superpowers, keeping entity/field names
  consistent with the surrounding artifact set.

## Reusing the shell seam

`configs/claude/scripts/spec_review.sh` exposes the discovery as composable functions that
emit `role<TAB>path` lines — `resolve_artifacts [ROOT]` (honors `$SPEC`/`$PLAN`/`$TASKS`,
else `discover_artifacts`). A skill that needs the same resolution in shell should source or
shell out to these rather than re-deriving the globs, so the layout rules live in exactly one
place.
