## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-02-11 - Consensus Loop Optimization
**Learning:** In string-processing loops involving dictionaries and manual counting (e.g., counting word occurrences in agent outputs), using `collections.Counter()` combined with set comprehensions (`{word for word in words}`) is significantly faster (~20%) and reduces manual iteration overhead compared to using standard dictionaries (`{}`) with `.get(key, 0) + 1` and explicit `set()` constructions.
**Action:** Default to `collections.Counter` and comprehension syntax when performing occurrence counting or building frequency maps over text data.
