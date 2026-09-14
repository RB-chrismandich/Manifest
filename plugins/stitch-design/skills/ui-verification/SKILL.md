---
name: ui-verification
description: Review an exact UI candidate read-only and return bounded evidence-based verdicts.
---

# UI verification lifecycle

Receive the approved task, exact candidate revision/hash, capture recipes, and freshly authorized `@ui_review` digest from `/stitch-design:ui-delivery`. Use the OMP-only `ui-reviewer` read-only and validate its output against `references/review.schema.json`. Bind every capture and finding to that candidate identity and reviewer digest; never write, run a build check, or request a retry without a new authorized repair cycle. The coordinator maps accepted to verified, repair_required to unverified, blocked to blocked, and failed to failed only after validating the strict schema and exact candidate identity. Skipped, unavailable, wrong-route, or stale evidence is unverified and prevents a green verdict. After two repair cycles with open findings, return blocked.
