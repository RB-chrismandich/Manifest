---
name: ui-verification
description: Review an exact UI candidate read-only and return bounded evidence-based verdicts.
---

# UI verification lifecycle

Receive the approved task, exact candidate revision/hash, and capture recipes from `/stitch-design:ui-delivery`. Use the OMP-only `ui-reviewer` read-only and validate its output against `references/review.schema.json`. Bind every capture and finding to that candidate identity; never write or request a retry without a new authorized repair cycle. Return verified, failed, blocked, or unverified evidence. A skipped or unavailable check is unverified and prevents a green verdict. After two repair cycles with open findings, return blocked.
