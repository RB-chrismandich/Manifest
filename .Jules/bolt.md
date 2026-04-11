# Bolt Learnings

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops
(e.g., 0.1s sleep) creates significant overhead due to process forking.
Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this
overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-02-12 - Asyncio Thread Offloading

**Learning:** Synchronous file I/O operations (like `open().write()` and
`json.dump()`) block the main event loop in high-concurrency async Python
scripts, potentially causing streaming lag or delays.

**Action:** Use `asyncio.to_thread()` to offload these blocking operations to
separate threads, and `asyncio.gather()` to execute them concurrently,
freeing up the event loop for other tasks.
