---
name: skill-evolve
description: Preview skill proposals stored in XDG data and require a separate explicit repository workflow before opening a review PR.
---

# Skill Evolve

Run `scripts/skill_evolve.py --json` to inspect proposals below
`$XDG_DATA_HOME/manifest/skill-evolve/`. Preview is read-only.

`--apply` intentionally returns a structured degraded result: repository
mutation and PR creation require a separate explicit workflow with a chosen
repository, forge, and authorization. Never discover another harness's
transcripts or mutate an installed skill tree.
