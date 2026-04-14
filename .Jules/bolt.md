# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-04-14 - Python Async I/O Threading

**Learning:** Writing multiple output files synchronously in an async loop
blocks the main event loop, causing overhead when many agents finish at once
in high concurrency environments.
**Action:** Use `asyncio.to_thread()` and `asyncio.gather()` to offload
blocking file operations (`json.dump`, `open().write()`, `Path.mkdir()`) to
prevent blocking the event loop.
