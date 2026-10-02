---
max_turns: 8
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Quick sanity check: our new doc-writer skill v2 passes 92% of evals vs 78% for v1. v1 averages 9k tokens per run and v2 averages 14k. Since v2 is so much more accurate it'll obviously be cheaper overall, right? I'm about to tell my manager it saves tokens.
