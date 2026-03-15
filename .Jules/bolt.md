# Bolt Performance Learnings

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops
(e.g., 0.1s sleep) creates significant overhead due to process forking.
Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this
overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-02-28 - Consensus Calculation Optimization

**Learning:** Replacing manual dictionary counting loops with
`collections.Counter` and utilizing set comprehensions with
`set().union(*iterable)` yields up to a ~15-20% performance improvement in
Python for calculating word frequencies and overlaps.

**Action:** When determining overlaps or intersections across multiple datasets,
leverage optimized C-backend operations like `set().union(*iterable)` and
`collections.Counter(chain.from_iterable(...))` instead of iterative `.update()`
and manual counter updates.
