## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-02-11 - Python collections.Counter vs Manual Dictionary Count Performance
**Learning:** Replacing manual dictionary counting loops with `collections.Counter` and set comprehensions (e.g., `Counter().update({x for x in y})`) yielded up to a ~15-20% performance improvement in consensus score calculation synthetic benchmarks. Also using `sum(1 for x in iterable if condition)` is faster and prevents memory allocation overhead compared to evaluating booleans inside the generator like `sum(condition for x in iterable)`.
**Action:** When counting word occurrences or intersections across multiple datasets in tight loops, prefer `collections.Counter()` combined with set comprehensions over manual dictionary inserts and updates.
