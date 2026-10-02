---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
I'm adding a `momentum_score` column to our `snapshots` SQLite table. The
population wiring is already done and working — I just want the schema itself to
reject bad data. What DDL do I need to add a `CHECK` constraint enforcing
`momentum_score >= 0` (or NULL) on that column?
