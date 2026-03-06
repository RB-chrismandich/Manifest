# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-02-27 - Python Dictionary vs Counter Performance

**Learning:** Replacing manual dictionary counting loops with `collections.Counter`
and utilizing set comprehensions (e.g., `{x for x in y}`) instead of passing a
generator to the `set()` constructor (`set(x for x in y)`) yields significant
performance improvements (up to ~30% in synthetic benchmarks) when calculating
consensus or counting occurrences.

**Action:** Always prefer `collections.Counter` and set comprehensions over
manual dictionary loops and `set(generator)` for counting or unique word
extraction.
