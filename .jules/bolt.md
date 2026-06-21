## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant
overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2025-06-08 - Counter Optimization

**Learning:** For counting word frequencies or frequencies of an arbitrary element, `collections.Counter`
with a generator or set comprehension is significantly faster than manual dictionary updates with nested
loops (`dict.get(key, 0) + 1`) and intermediate `set` merging. `Counter` is implemented in C and avoids
the overhead of manually running python statements for each word.

**Action:** Always prefer `collections.Counter` with generator comprehensions for counting frequencies
rather than manually updating a dictionary.

## 2025-02-21 - Python Parsing Optimization

**Learning:** To improve performance when filtering large log files or line-delimited JSON data, calling
`json.loads()` multiple times on the same line across different iterations is a significant bottleneck.

**Action:** Parse the JSON once per line during the initial pass and store the original line alongside
the extracted data in a tuple or structure (e.g., `parsed_lines.append((ln, extracted_id))`) for
subsequent O(1) checks.

## 2026-06-09 - Exception Overhead in Hot Paths

**Learning:** Catching `ValueError` exceptions (e.g., when calling `json.loads` on non-JSON strings)
inside tight loops or large parsing pipelines creates significant performance overhead (tested at ~2.8x slower).

**Action:** Use fast-path checks (such as stripping whitespace and checking if the first character is a
valid JSON opening char like `{`, `[`, `"`, `t`, `f`, `n`, or a digit) to bypass the exception overhead
for obvious string literals.

## 2026-06-16 - JSONL Parsing Fast-Path Optimization

**Learning:** Calling `.strip()` on every line of a large JSONL file and risking `json.loads` exception
overhead on non-JSON lines adds significant performance overhead. Replacing `.strip()` with a direct check
for the first character (e.g., `if not line or line[0] != '{': continue`) bypasses both the string allocation
of `.strip()` and the exception overhead for noise lines, yielding ~45% faster parse times.

**Action:** When parsing large, homogeneous JSONL files where the target lines consistently start with a specific
character (like `{`), use direct prefix checks (`line[0]`) to filter lines before calling `json.loads`.
