## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-02-07 - Python Async I/O & Counter
**Learning:** In async contexts, blocking I/O (like json.dump or open().write) and manual dictionary counting loops introduce unnecessary event-loop blocks and performance overhead.
**Action:** Use `asyncio.to_thread` for blocking file writes and operations, and replace manual loops for element counting with `collections.Counter` with `itertools.chain.from_iterable()` for a measurable speed boost.
