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

## 2026-06-21 - Generator vs list comprehension for counting (small, cold paths)

**Learning:** `len([1 for ... if cond])` is measurably faster than `sum(1 for ... if cond)` on
small/medium inputs: the list comprehension runs in a tight C loop and avoids the per-item
generator `next()` overhead (benchmarked ~40% faster at n=50–500, collapsing to ~2% by n=5000
as list-allocation cost catches up). The tradeoff is memory — `len([...])` materializes a
throwaway list (O(k)) where `sum(genexpr)` is O(1) — so it only pays off on small, bounded
inputs in cold paths, not in genuinely hot loops over large data.

**Action:** Replaced `sum(1 for count in word_counts.values() if count > 1)` with
`len([1 for count in word_counts.values() if count > 1])` in `configs/claude/scripts/agents/orchestrator.py`,
which is the once-per-run consensus calc over a few hundred words — small input, cold path. For
large or memory-sensitive loops keep `sum(1 for ...)` to avoid the list allocation. Unrelated to
set-vs-list membership: prefer a `set` for membership tests (O(1) vs O(n)); do not swap a set
comprehension for a list to "save allocation."

## 2026-06-21 - Memory Optimization for Large Files

**Learning:** When dealing with large files, creating intermediate lists (like `parsed_lines`) causes
peak memory usage to skyrocket.
**Action:** Use a two-pass lazy iteration approach instead to identify what to keep and then collect it.

## 2026-06-21 - JSONL Parsing Optimization Tradeoffs

**Learning:** When applying fast-path prefix checks for JSON parsing, replacing `line.strip()` with
`line.isspace()` or complex whitespace skipping rules (like `line.lstrip()[:1]`) is significantly slower
than simply checking the first character (`line[0]`). Testing on a file with millions of noise lines
showed `line[0] != '{'` is over 1000x faster than `.isspace()` because it avoids all string
iteration/allocation.
**Action:** When implementing fast-path checks for JSON, lead with the cheap `line[0] != '{'` character
check as a short-circuit so the common (unpadded) case never pays for whitespace handling, then fall back
to `line.lstrip()[:1] != '{'` only for the lines that fail that first check (`line[0] != '{' and
line.lstrip()[:1] != '{'`). This keeps whitespace-padded valid JSON — which `lstrip` still recognizes —
instead of dropping it to the `json.loads` exception path, while the `line[0]` guard keeps the hot path
fast because `lstrip` runs only on the rare non-`{`-leading lines. Keep the `lstrip` clause: it is what
preserves padded JSON, and the guard already spares the common case its cost.

## 2026-06-25 - Double File Reads in Hot Paths

**Learning:** Calling `Path.read_text()` twice on the same file in a tight loop or check branch (e.g.,
`if func(f.read_text()) != f.read_text():`) is a significant performance bottleneck. It causes the entire file
to be read from disk, decoded, and allocated in memory twice per file.

**Action:** Read the file content once into a local variable (`content = f.read_text()`) and use that variable
for both the transformation and the equality check.

## 2026-06-30 - Fast Path Substring check

**Learning:** Using `if '"test"' in content` before parsing `json.loads` avoids massive JSONDecodeError and
allocation times when target strings are entirely absent in large documents (like `package.json` or `Makefile`).
**Action:** When scanning entire file contents (e.g., `package.json` or `Makefile`) for specific keys or patterns,
utilize a fast substring check (e.g., `'"test"' in content`) to short-circuit and bypass expensive parsing operations
like `json.loads()` or `re.search()` if the target is absent.

## 2026-06-30 - Fast-Path JSON Parsing for Argument Values — RETRACTED 2026-08-26

**Retracted.** This learning was applied to `audit.py` and `ingest.py`, then reverted by #832 and re-proposed
again by #841 because this entry still recommended it. Do not re-apply it.

**Why it was reverted:** the fast path hand-rolls an allowlist of JSON-leading characters
(`'{["tf-0123456789NIn'`), duplicating the parser's own acceptance grammar. A shadow grammar drifts from the real
one, and these call sites are fail-open background ingest paths where the exception cost is on no hot user-facing
loop. The `except json.JSONDecodeError` branch already does exactly what the fast path did — `continue` in
`parse_transcript`/`trim`, `out[k] = v` in `_parse_kv` — so the optimization bought nothing but a second copy of
the grammar. Differential-tested over 40 adversarial inputs: zero behavioural divergence.

**Action:** Let `json.loads` raise and handle it in `except`. Do not pre-filter by leading character.

## 2026-06-30 - Iter vs While Walrus Operator for File Reads — CLAIM CORRECTED 2026-08-26

The code change (`while chunk := stream.read(n):` over `iter(lambda: stream.read(n), b"")`) landed in #834 and is
fine: for `bytes`, `b""` is the only falsy value, so the two forms are equivalent at every digest call site, and
the walrus form additionally survives a raw non-blocking stream returning `None`.

**The performance claim did not survive measurement.** The original entry asserted "~15-20% faster for large
files". Re-measured over a 256MB file, sha256, median of 7 **interleaved alternating-order** trials:

| chunk | iter | walrus | delta |
|---|---|---|---|
| 1024 KB | 863.0 ms | 884.8 ms | -2.5% |
| 64 KB | 882.4 ms | 894.3 ms | -1.3% |

Both within run-to-run variance. A naive **non-interleaved** run first showed walrus 19.6% *slower* at 64KB — a
warm-cache ordering artifact, and exactly how a "15-20% faster" number gets produced.

**Action:** Prefer the walrus form for readability, not for speed. Benchmark by interleaving alternating trials
and reporting a median; a sequential A-then-B run measures page cache, not code.
