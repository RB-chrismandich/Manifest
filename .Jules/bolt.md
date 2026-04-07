# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-02-08 - Asyncio Event Loop Blocking

**Learning:** Performing synchronous, blocking file I/O operations (like
`open().write()` or `Path.mkdir()`) directly in an `async` function blocks the
asyncio event loop. In high-concurrency scripts like `parallel_agent.py`, this
introduces significant lag (e.g., waiting ~0.45s to write 1000 files vs
~0.009s actual write time).
**Action:** In async contexts (Python 3.9+), use `asyncio.to_thread()` to
offload blocking I/O operations to a separate thread, preserving event loop
responsiveness.
