## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant
overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2025-06-08 - Counter Optimization

**Learning:** For counting frequencies, `collections.Counter` with a generator or set comprehension is significantly
faster than manual dictionary updates with nested loops (`dict.get(key, 0) + 1`) and intermediate `set` merging.
`Counter` is implemented in C and avoids the overhead of manually running python statements for each word.
**Action:** Always prefer `collections.Counter` with generator comprehensions for counting frequencies.

## 2025-02-21 - Python Parsing Optimization

**Learning:** To improve performance when filtering large log files or line-delimited JSON data, calling `json.loads()`
multiple times on the same line across different iterations is a significant bottleneck.
**Action:** Parse the JSON once per line during the initial pass and store the original line alongside the extracted
data in a tuple or structure for subsequent O(1) checks.

## 2026-06-09 - Exception Overhead in Hot Paths

**Learning:** Catching `ValueError` exceptions (e.g., when calling `json.loads` on non-JSON strings) inside tight
loops or large parsing pipelines creates significant performance overhead (tested at ~2.8x slower).
**Action:** Use fast-path checks (such as stripping whitespace and checking if the first character is a valid JSON
opening char like `{`, `[`, `"`, `t`, `f`, `n`, or a digit) to bypass the exception overhead for obvious string
literals.

## 2026-06-17 - List Comprehensions vs. Generators

**Learning:** In hot loops, list comprehensions execute at C speed without yielding overhead (e.g.,
`len([1 for x in iter if cond])` is faster than `sum(1 for x in iter if cond)`). Furthermore, evaluating truthiness
against a list of keys instead of a set avoids set construction overhead in tight loops.
**Action:** Use list comprehensions with `len()` instead of generator expressions with `sum(1)` for counting items on
hot paths.
