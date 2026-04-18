# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops
(e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over
external commands inside loops.

## 2024-04-18 - Blocking I/O in Async Python Methods

**Learning:** Blocking I/O operations (like `open().write()`, `json.dump()`, or
`Path.mkdir()`) within `async def` methods in high-concurrency orchestration
scripts block the Python event loop and cause performance bottlenecks.

**Action:** Use `asyncio.to_thread()` combined with `asyncio.gather()` to safely
offload synchronous I/O and execute it concurrently without blocking the event
loop.
