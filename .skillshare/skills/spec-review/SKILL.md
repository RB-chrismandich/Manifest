---
name: spec-review
description: |
  Cross-reference a project's spec / plan / tasks artifacts for internal
  consistency using an independent model (Gemini), and surface structured
  remediation guidance (Location / Gap / Recommended Direction / Reason Why).
  Analysis-only — never edits artifacts. Works with both speckit
  (spec.md/plan.md/tasks.md) and superpowers (design + plan-with-embedded-tasks)
  layouts. Auto-discovers artifacts, or pass explicit paths.
---

# Spec Review (Gemini cross-reference)

Run an independent, analysis-only consistency check across the project's planning
artifacts. A second model (Gemini) reviews what Claude authored — catching
structural blind spots that self-review misses.

## How to run

```bash
# Auto-discover spec/plan/tasks under the current project and review:
~/.claude/scripts/spec_review.sh

# Explicit artifacts:
~/.claude/scripts/spec_review.sh --spec ./spec.md --plan ./plan.md --tasks ./tasks.md

# Machine-readable:
~/.claude/scripts/spec_review.sh --format json
```

Findings print as a tree of `CLARIFICATION REQUIRED` blocks, or
`✓ No inconsistencies found.` Requires the `gemini` CLI (logged in). This skill is
analysis-only; apply the recommendations yourself.
