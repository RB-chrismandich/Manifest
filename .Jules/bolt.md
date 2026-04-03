# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s
sleep) creates significant overhead due to process forking. Replacing `date +%s`
with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over
external commands inside loops.

## 2026-04-03 - Offload Blocking I/O

**Learning:** In async contexts (Python 3.9+), use `asyncio.to_thread()` to
offload blocking I/O operations like `json.dump`, `open().write()`, or
`Path.mkdir()` to a separate thread. This prevents blocking the event loop and
significantly reduces lag in high-concurrency scripts like `parallel_agent.py`.

**Action:** Always wrap synchronous disk or network operations in
`asyncio.to_thread` when executing inside an `async def` function.
