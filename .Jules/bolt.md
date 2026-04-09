## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-04-09 - Asyncio File I/O Optimization
**Learning:** Sequential, synchronous file I/O operations (like `open().write()` and `json.dump()`) inside an async function block the event loop. In high-concurrency applications, offloading these to separate threads via `asyncio.to_thread()` and running them concurrently with `asyncio.gather()` prevents blocking and reduces total execution time.
**Action:** Use `asyncio.to_thread()` and `asyncio.gather()` when performing multiple blocking file I/O operations within async functions to avoid stalling the event loop.
