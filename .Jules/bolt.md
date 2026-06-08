## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2025-06-08 - Counter Optimization
**Learning:** For counting word frequencies or frequencies of an arbitrary element, `collections.Counter` with a generator or set comprehension is significantly faster than manual dictionary updates with nested loops (`dict.get(key, 0) + 1`) and intermediate `set` merging. `Counter` is implemented in C and avoids the overhead of manually running python statements for each word.
**Action:** Always prefer `collections.Counter` with generator comprehensions for counting frequencies rather than manually updating a dictionary.
