---
name: spec-review
description: Use before finalizing spec/plan/tasks — cross-reference for internal consistency via the parallel-agent panel (excluding the author), deduped findings. Analysis-only, never edits. Speckit/superpowers; auto-discovers or explicit paths.
---

# Spec Review (parallel-agent cross-reference)

Run an independent, analysis-only consistency check across the project's planning
artifacts. The parallel-agent panel — every enabled agent **except** the author
(Claude) — reviews what Claude wrote, and their findings are synthesized into one
deduped list. Multiple independent reviewers catch structural blind spots a single
model (or self-review) misses.

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
`✓ No inconsistencies found.` Requires `[[skill:parallel-agent]]` plus at least one
non-Claude agent CLI; it falls back to a single `agy` review when the panel is
unavailable. This skill is analysis-only; apply the recommendations yourself.

Layout detection (speckit `spec/plan/tasks` vs superpowers `design + plan`, with
tasks embedded in the plan) follows `configs/claude/references/spec-artifact-discovery.md`
— the same contract `spec-audit-tasks` and `spec-decide-tradeoffs` use — and is
implemented by the script's `resolve_artifacts`/`discover_artifacts` seam.
