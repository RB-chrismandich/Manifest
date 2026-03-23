## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2025-02-28 - Optimizing `_calculate_consensus` with Counter and chain
**Learning:** Replacing manual dictionary counting loops with `collections.Counter` combined with `itertools.chain.from_iterable()` and utilizing set comprehensions yields up to a ~15-20% performance improvement by leveraging optimized C-backend operations. Additionally, unpacking an iterable of sets into `set().union(*iterable)` (or `set.union(*iterable)`) leverages highly optimized C-backend operations, significantly outperforming iterative manual loops or `.update()` calls.
**Action:** When combining multiple sets, use `set().union(*iterable)`. When counting word frequencies across iterables, use `collections.Counter(itertools.chain.from_iterable(items))` instead of manually maintaining a dictionary and updating it iteratively.
