---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our `filings` table already has the right ingestion design (append-only, decided
months ago and working fine). What's slow now is querying it: `SELECT * FROM
filings WHERE filer = ? AND filed_at BETWEEN ? AND ? ORDER BY filed_at DESC` takes
2 seconds on 5M rows. What index should I add to speed this up?
