---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Benchmark these two ways of joining 10,000 strings in Python — `''.join(list)` vs `+=` in a loop — using timeit, and tell me which is faster.
