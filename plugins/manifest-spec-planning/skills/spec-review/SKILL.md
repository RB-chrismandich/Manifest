---
name: spec-review
description: Cross-reference spec/plan/tasks artifacts for internal consistency through a selected native reviewer. Analysis-only, never edits. Speckit and superpowers layouts; auto-discovers or takes explicit paths.
---

# Spec Review

Run an independent, analysis-only consistency check across the project's planning
artifacts. The bundle invokes `agy` by default, or the native reviewer selected
through `SPEC_REVIEW_CLI` and `SPEC_REVIEW_PROVIDER`. It returns non-zero when
the output cannot be verified as `NO_ISSUES` or a structured clarification.

## How to run

```bash
# Auto-discover spec/plan/tasks under the current project and review:
../../runtime/spec_review.sh

# Explicit artifacts:
../../runtime/spec_review.sh --spec ./spec.md --plan ./plan.md --tasks ./tasks.md

# Machine-readable:
../../runtime/spec_review.sh --format json
```

Findings print as `CLARIFICATION REQUIRED` blocks or a clean result. The
reviewer executable must already be installed; this runtime never installs a
CLI or reads another bundle. This skill is analysis-only; apply recommendations
yourself.

Layout detection (speckit `spec/plan/tasks` vs superpowers `design + plan`, with
tasks embedded in the plan) follows `../../runtime/references/spec-artifact-discovery.md`
— the same contract `spec-audit-tasks` and `spec-decide-tradeoffs` use — and is
implemented by the script's `resolve_artifacts`/`discover_artifacts` seam.
