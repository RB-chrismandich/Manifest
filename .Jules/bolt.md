## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-02-12 - Word Count Performance in Python
**Learning:** Using `collections.Counter.update()` with set comprehensions (`{word for word in output...}`) is about 15% faster for calculating string frequency distribution than iterating over generators and updating a standard python dict (`word_counts.get(word, 0) + 1`). This bypasses Python-level loop overhead by delegating to C implementations within `collections.Counter`.
**Action:** Always use `collections.Counter` along with set comprehensions for tallying elements across collections.
