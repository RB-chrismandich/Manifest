# Contract: Merged Skill SKILL.md

A survivor skill that absorbed variants MUST satisfy:

```markdown
---
name: <survivor-name>            # == directory name
description: <single description covering ALL absorbed trigger conditions;
  mentions the distinct modes/scopes so triggering matches any variant's
  former audience>
---

# <Title>

<shared procedure core>

## Mode/Scope subsections (one per absorbed variant's distinct scope)
e.g. for live-data-validation: "Smoke", "Before merge", "After green tests"
e.g. for verify-premise: "CLI/binary", "API schema", "Image runtime contract"

<each subsection: only the steps that DIFFER from the shared core>
```

Rules:
- Every distinct trigger condition and procedure step from each absorbed
  variant appears exactly once (shared core or its subsection). Conflicting
  guidance → stricter rule wins, noted inline.
- No `(formerly X)` aliases in the description (wastes trigger tokens) —
  absorbed names listed in a single line at the bottom of the body:
  `> Absorbed: <name1>, <name2> (2026-06)` — this also lets the evolve
  library prompt's description matching suppress re-proposals.
- For the keep-both cluster (reset-reapply-clean-pr / clean-pr-from-stale-base):
  each body gains one decision-anchor line:
  "If <root cause is the other's>, use <other-skill-name> instead."
