## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-06-08 - Counter Optimization

**Learning:** For counting word frequencies or frequencies of an arbitrary
element, `collections.Counter` with a generator or set comprehension is
significantly faster than manual dictionary updates with nested loops
(`dict.get(key, 0) + 1`) and intermediate `set` merging. `Counter` is
implemented in C and avoids the overhead of manually running python statements
for each word.
**Action:** Always prefer `collections.Counter` with generator comprehensions
for counting frequencies rather than manually updating a dictionary.

## 2025-02-21 - Python Parsing Optimization

**Learning:** To improve performance when filtering large log files or
line-delimited JSON data, calling `json.loads()` multiple times on the same
line across different iterations is a significant bottleneck.
**Action:** Parse the JSON once per line during the initial pass and store the
original line alongside the extracted data in a tuple or structure (e.g.,
`parsed_lines.append((ln, extracted_id))`) for subsequent O(1) checks.

## 2025-10-23 - Python Parsing ValueErrors Overhead

**Learning:** Calling `json.loads()` on normal strings (like configuration
values, e.g., `key=value`) raises a `ValueError`. Python exception handling is
relatively slow. In tight loops or large file parsers, raising and catching
these exceptions for normal string data creates significant, measurable
performance overhead.
**Action:** When parsing mixed JSON/string key-value pairs, use a fast-path
character check (e.g., `if v and v[0] in '{["tf0123456789-n':`) before
calling `json.loads()` to bypass the JSON parser and prevent the exception
entirely for obvious string values.
