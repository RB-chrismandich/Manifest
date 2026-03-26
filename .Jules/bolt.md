# Bolt's Performance Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops
(e.g., 0.1s sleep) creates significant overhead due to process forking.
Replacing `date +%s` with the builtin `$SECONDS` variable eliminates
this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-02-07 - Python Word Counting Optimization

**Learning:** Manual dictionary counting loops and `set.update()` operations
in Python are slow. Replacing them with list comprehensions for sets,
`itertools.chain.from_iterable()`, and `collections.Counter` yields
significant performance improvements by leveraging optimized C-backend
operations.
**Action:** Use `collections.Counter(itertools.chain.from_iterable(...))`
for counting items across multiple iterables instead of nested loops and
manual dictionary increments.
