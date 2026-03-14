# Bolt Critical Learnings

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2024-03-08 - Python Set Comprehensions and Counter

**Learning:** Replacing manual dictionary counting loops with
`collections.Counter` and utilizing set comprehensions yielded significant
performance improvements in synthetic benchmarks for dictionary operations.
**Action:** Always prefer built-in tools like `collections.Counter` for
counting items, and use comprehensions instead of manual loops for better
performance.
