## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-03-01 - Python Loop Performance
**Learning:** Using `collections.Counter` with a set comprehension (`{x for x in y}`) to count unique occurrences within loops is significantly faster (up to ~30%) than using nested loops, manual dictionary updates (`dict.get(x, 0) + 1`), and `set(generator_expression)`.
**Action:** Always prefer `Counter` and set comprehensions over manual tallying and `set()` constructors when aggregating distinct elements across collections in Python.
