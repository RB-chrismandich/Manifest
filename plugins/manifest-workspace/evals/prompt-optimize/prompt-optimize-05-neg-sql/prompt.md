---
max_turns: 4
timeout_seconds: 120
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Optimize this query, it's slow on a 50M-row table:

SELECT * FROM orders WHERE YEAR(created_at) = 2025 AND status = 'shipped' ORDER BY created_at DESC;
