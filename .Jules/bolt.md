# Bolt Critical Learnings

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-03-16 - Python Set Union and Counter Performance

**Learning:** Replacing manual dictionary counting loops with
`collections.Counter` and utilizing set comprehensions with
`set().union(*iterable)` in Python yields up to a ~15-20% performance
improvement by leveraging highly optimized C-backend operations, significantly
outperforming iterative manual loops or `.update()` calls.
**Action:** Always use `set.union(*iterable)` and `collections.Counter` instead
of manual Python loops and `.update()` when combining sets or counting
frequencies across large collections.
