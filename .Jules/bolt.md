## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-02-07 - collections.Counter Performance
**Learning:** Manual dictionary updates with nested loops (`dict.get(key, 0) + 1`)
and intermediate `set` merging (`set.update()`) for frequency counting creates
unnecessary Python-level overhead. `collections.Counter` provides an optimized
C-level implementation that is significantly faster for text processing tasks
like cross-verification consensus scoring. Passing a generator or set
comprehension directly to `Counter.update()` avoids instantiating additional
intermediate sets.
**Action:** Always prefer `collections.Counter` over manual dictionary loops for
frequency counting or aggregation tasks.
