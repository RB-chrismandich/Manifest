---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Create `mathutil.py` with `def clamp(x, lo, hi): return max(lo, min(x, hi))`, then write a short test file `test_mathutil.py` for it (pytest, or stdlib `unittest` if pytest isn't usable here) and run it.
