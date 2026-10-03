---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Fix issue #11: exports truncate at 10k rows. The export code does `rows = query.limit(10000).all()` in src/export.py. What's the fix?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
