# Bolt Learnings

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over
external commands inside loops.

## 2023-10-27 - Optimize _calculate_consensus in parallel_agent.py

**Learning:** Replacing manual dictionary counting loops with
`collections.Counter` and utilizing set comprehensions combined with
`set().union(*iterable)` yields up to a ~15-20% performance improvement in
python.

**Action:** Use `collections.Counter` and `set().union(*iterable)` instead of
manual iterative manual loops or `.update()` calls when combining multiple sets
and counting words.
