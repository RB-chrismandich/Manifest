# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-02-28 - Set Comprehensions and Counter Optimization

**Learning:** Manual nested loops, explicit `set(generator)` instantiations,
and custom dictionary tracking are noticeably slower than using native
`collections.Counter()` combined with set comprehensions (`{x for x in ...}`).
Using `sum(1 for ...)` is also slightly faster and more memory-efficient than
`sum(bool ...)`. Combining these results in up to ~30% faster execution on large
strings for repetitive text analysis.
**Action:** When calculating word frequencies or computing consensus from strings,
prefer `collections.Counter()` updated via set comprehensions.
