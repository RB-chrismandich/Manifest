# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-03-07 - Python Consensus Calculation Performance

**Learning:** Replacing manual dictionary counting loops with
`collections.Counter` and utilizing set comprehensions (e.g.
`{word.lower() for word in output.split() if len(word) > 4}`) in
`parallel_agent.py`'s `_calculate_consensus` method yielded up to a ~20-30%
performance improvement in benchmarks by preventing unnecessary memory
allocations and set unions.

**Action:** Prefer `collections.Counter` with the `update` method and set
comprehensions for frequency counting of unique elements in text processing
loops.
