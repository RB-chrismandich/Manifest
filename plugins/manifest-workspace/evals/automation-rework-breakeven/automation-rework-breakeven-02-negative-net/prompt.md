---
max_turns: 8
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Deciding between two versions of our PR-triage automation. v1: 20k tokens/run. v2: 24k tokens/run, more thorough. When v1 gets it wrong the output is confidently wrong, so recovery basically means redoing the whole thing — we measured that at ~25k tokens. Observed v1 miss rate is 10%; v2 hasn't needed a redo in our evals. Should we move to v2?
