# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-02-28 - Fast Set Intersection and Frequency Counting

**Learning:** Manual dictionary updates in a loop and single `.update()`
calls for accumulating sets represent a CPU bottleneck in Python, particularly
in data-processing loops like parallel agent consensus scoring. Replacing
manual iterative counting with `collections.Counter` and
`itertools.chain.from_iterable()` combined with unpacking an iterable into
`set().union(*iterable)` pushes the execution down to optimized C
implementations, resulting in faster and cleaner code.
**Action:** When gathering frequency counts over a collection of strings or
sets in hot-paths, always use `collections.Counter(itertools.chain.from_iterable(...))`
and combine sets with `set().union(*iterable)` instead of explicit loops.
