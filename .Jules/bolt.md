# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-02-07 - Python Iterable Optimization

**Learning:** Replacing manual dictionary counting loops with
`collections.Counter` combined with `itertools.chain.from_iterable()`,
utilizing set comprehensions, and unpacking lists into `set.union(*iterable)`
yields up to a ~15-20% performance improvement by leveraging optimized C-backend
operations.

**Action:** Prefer `collections.Counter` and `itertools` for aggregating or
merging elements across nested arrays or sets instead of manual dictionary
increments and `set.update()` loops.
