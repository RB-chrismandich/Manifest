# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over
external commands inside loops.

## 2025-02-28 - Optimizing String Iteration and Word Counting in Python

**Learning:** Using manual loops combined with `dict.get(key, 0) + 1` for
counting word frequencies inside iteration blocks introduces high overhead.
Using `set(generator)` also introduces extra allocations when computing sets on
the fly.

**Action:** Always prefer `collections.Counter` for frequency counting which
delegates work to optimized C code. Additionally, use set comprehensions
(e.g., `{x for x in y}`) which are significantly faster than generating an
iterable inside `set()`. Apply these patterns across any loops dealing with
large text extraction or processing.
