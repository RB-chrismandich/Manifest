---
name: spec-review
description: Cross-reference spec/plan/tasks artifacts for internal consistency using Antigravity/agy; surfaces structured remediation guidance. Analysis-only, never edits. Works with speckit (spec.md/plan.md/tasks.md) and superpowers layouts; auto-discovers or takes explicit paths.
---

# Spec Review (Antigravity cross-reference)

Run an independent, analysis-only consistency check across the project's planning
artifacts. A second model (Antigravity / `agy`) reviews what Claude authored — catching
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
`✓ No inconsistencies found.` Requires the `agy` CLI (logged in). This skill is
analysis-only; apply the recommendations yourself.
