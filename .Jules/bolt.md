# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-03-10 - Fast string processing with collections.Counter and Sets

**Learning:** In Python, avoiding nested loops and explicitly tracking sets
when processing word frequencies is more efficient. Iterating with set
comprehensions to directly pass words to `collections.Counter.update` methods
resulted in a ~14% improvement in a simulated text consensus method (simulating
LLM agents' output).

**Action:** When gathering frequency counts of unique items per document across
a large array of text documents, replace `for` loop updates and manual
dictionary counting with `collections.Counter().update({set comprehension})`.
Additionally, when computing the final count of items meeting a condition, use
generator comprehension with `sum(1 for ... if ...)` instead of `sum(condition
for ...)`.
