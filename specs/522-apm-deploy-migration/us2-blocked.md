# US2 Is Blocked: apm Cannot Replace the Cursor Generators

**Produced by**: T025 (the equivalence harness that gates T028/T030)
**Measured**: 2026-07-27 · **Result**: ⛔ **there is nothing to be equivalent to**

## The measurement

A real 108-skill package, installed with `--target claude,cursor` into an
isolated `HOME`:

```text
~/.claude/skills   108 SKILL.md
~/.cursor          0 files
```

apm's own install output names the reason:

```text
Some primitives are not supported: cursor (instructions); ...
```

Cursor's rule format (`.mdc` files carrying `description` + `globs` frontmatter)
**is** Cursor's instructions primitive. apm does not deploy it, so it produces no
`.mdc` output at any target setting.

Meanwhile `generate_cursor_rules.sh` produces **110 `.mdc` files** today.

## What this blocks, and why the ordering saved us

US2's premise — recorded in `spec.md`'s scope table — is that the three
per-harness generators are "replaceable by a harness-targeted build". For
`generate_cursor_rules.sh` that is **false**, and the two tasks scheduled to act
on it are irreversible:

| Task | Planned action | Consequence if run today |
|---|---|---|
| **T025** | build an equivalence harness comparing legacy vs APM output | **No subject.** APM output is the empty set; an equivalence check would compare 110 files against 0 |
| **T026** | functional consumption check — confirm a real harness loads the new output | Nothing to load |
| **T028** | delete `generate_cursor_rules.sh`, `generate_cursor_agents.py`, `generate_cursor_mcp.py` | **Deletes a live capability with no replacement** |
| **T030** | remove the 109 committed `.mdc` artifacts from version control | **Removes Cursor's rule integration entirely** |

T027 was deliberately sequenced before the deletions, and T025/T026 were
deliberately made preconditions of T028. That ordering is what caught this
before anything was deleted. Had T028 run on schedule, Cursor would have lost
its rule integration with no way to regenerate it — the generators would be gone
and the artifacts untracked.

## An equivalence check that passes vacuously is the trap

The dangerous version of T025 is one that compares "files APM produced for
cursor" against "files APM produced for cursor" — both empty — and reports
equivalence. It would be green, and it would be evidence of nothing. Any harness
written here MUST assert its subject is **non-empty on both sides** before
comparing, which is the same precondition discipline FR-023 requires everywhere
else in this feature.

## Options

1. **Retain the cursor generators, like `generate_commands_doc.py`** (T029's
   precedent). They compile source primitives into a harness-specific format apm
   has no target for. This is the honest reading of the measurement and matches
   how the scripts domain was already handled in `migration-inventory.md`.
   Consequence: US2's "no hand-run generator remains" claim shrinks to the
   generators apm can actually replace — which, on this evidence, may be none.
2. **Contribute an instructions target to apm.** Out of scope for this feature
   and dependent on an upstream project.
3. **Drop Cursor rule support.** Not a migration; a feature removal, and it
   should be argued as one rather than arrived at by deleting a generator.

## Recommendation

Take option 1 and amend US2. The scope table's claim that these three generators
are "in scope — replaceable by a harness-targeted build" is now measured to be
wrong, in the same way `spec.md:36`'s retention claim was. It should be corrected
in the spec rather than worked around, and T028/T030 should be closed as **VOID —
no replacement exists** rather than left open to be executed later by someone who
does not read this file.
