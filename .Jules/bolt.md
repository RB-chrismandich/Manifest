# Bolt Performance Learnings

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-02-12 - Python Set Operations and Collections Performance

**Learning:** When calculating word consensus or performing heavy set
operations, using iterative manual dictionary counting loops is significantly
slower than using highly optimized C-backend operations like
`collections.Counter`, `set.union`, and `itertools.chain.from_iterable` on an
initial set comprehension. This refactor yields up to a ~15-20% performance
improvement.
**Action:** Use `collections.Counter` and `set.union` when processing large
collections or finding commonalities instead of manual loop updates to
maximize execution speed.
